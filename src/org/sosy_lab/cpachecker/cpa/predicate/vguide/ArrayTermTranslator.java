// This file is part of CPAchecker,
// a tool for configurable software verification:
// https://cpachecker.sosy-lab.org
//
// SPDX-FileCopyrightText: 2007-2024 Dirk Beyer <https://www.sosy-lab.org>
//
// SPDX-License-Identifier: Apache-2.0

package org.sosy_lab.cpachecker.cpa.predicate.vguide;

import com.google.common.collect.ImmutableMap;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.regex.Matcher;
import java.util.regex.Pattern;
import org.sosy_lab.cpachecker.cpa.predicate.BlockFormulaStrategy.BlockFormulas;
import org.sosy_lab.cpachecker.util.predicates.smt.FormulaManagerView;
import org.sosy_lab.java_smt.api.BooleanFormula;
import org.sosy_lab.java_smt.api.FormulaType;

/**
 * Bridges LLM source-level array reads (e.g. {@code (c i)} for {@code c[i]}) to the heap-select
 * encoding used by the CEGAR formulas (issues #58/#59/#60).
 *
 * <p>The CEGAR encoding has no array-value symbols: a C array is an address bitvector and an
 * element read is {@code (select *heap@N (+ addr@N (bvshl idx@K size)))}, usually wrapped in
 * let-defs. The LLM only knows source names, so its element-wise candidates could never be
 * parsed. Templates are extracted from the trace's own block formulas (select + bvadd + bvshl
 * shape, let-defs resolved); versions are applied later via {@link FormulaManagerView#instantiate}
 * with the target loop head's SSAMap — never guessed from text.
 */
final class ArrayTermTranslator {

  /** Unversioned access template for one C array. */
  record AccessTemplate(
      String heapVar, // unversioned heap array name, e.g. "*long_long_int"
      String addrVar, // unversioned address var, e.g. "main::c"
      String idxVar, // unversioned index var, e.g. "main::i"
      int shiftBits, // shift amount of the bvshl (log2 of byte size)
      int extractMsb, // index narrowing as seen in the trace (-1 = no narrowing)
      int extractLsb,
      int shiftConstBits, // width of the shift constant as seen in the trace
      FormulaType<?> arrayType) {

    /** Element size in bits (byte-addressed heaps: bits = (1 << shift) * 8). */
    int elementBits() {
      return (1 << shiftBits) * 8;
    }

    /** Source array name (e.g. "c" for main::c). */
    String addrSourceName() {
      return sourceNameOf(addrVar);
    }
  }

  private static final Pattern ARRAY_ACCESS =
      Pattern.compile("\\(([A-Za-z_]\\w*)\\s+([A-Za-z_]\\w*)\\)");
  private static final Pattern DECLARE_BV =
      Pattern.compile("\\(declare-fun\\s+([^ )]+)\\s+\\(\\)\\s+\\(_ BitVec\\s+(\\d+)\\)\\)");

  private static final Pattern DECLARE_ARRAY =
      Pattern.compile(
          "\\(declare-fun\\s+([^ )]+)\\s+\\(\\)\\s+\\(Array \\(_ BitVec\\s+(\\d+)\\) \\(_ BitVec\\s+(\\d+)\\)\\)");
  private final ImmutableMap<String, AccessTemplate> templates; // source array name -> template
  private final ImmutableMap<String, Integer> varBits; // "main::i" -> 64 (unversioned)
  private final ImmutableMap<String, Integer> arrayIndexBits; // heap -> declared index width
  private final Pattern bareIdentifierPattern; // precompiled alternation of bare names

  ArrayTermTranslator(
      ImmutableMap<String, AccessTemplate> templates, ImmutableMap<String, Integer> varBits) {
    this(templates, varBits, ImmutableMap.of());
  }

  ArrayTermTranslator(
      ImmutableMap<String, AccessTemplate> templates,
      ImmutableMap<String, Integer> varBits,
      ImmutableMap<String, Integer> arrayIndexBits) {
    this.templates = templates;
    this.varBits = varBits;
    this.arrayIndexBits = arrayIndexBits;
    List<String> keys = new ArrayList<>(varBits.keySet());
    keys.removeIf(k -> k.contains("::") || k.isEmpty());
    keys.sort((a, b) -> Integer.compare(b.length(), a.length()));
    StringBuilder alt = new StringBuilder();
    for (String k : keys) {
      if (alt.length() > 0) {
        alt.append('|');
      }
      alt.append(Pattern.quote(k));
    }
    this.bareIdentifierPattern =
        keys.isEmpty() ? null : Pattern.compile("(?<![A-Za-z0-9_@|:])(" + alt + ")(?![A-Za-z0-9_@|])");
  }

  /** Test convenience constructor (no declared-variable maps). */
  ArrayTermTranslator(ImmutableMap<String, AccessTemplate> templates) {
    this(templates, ImmutableMap.of());
  }

  /** Extracts array-access templates and declared variable sizes from the trace's formulas. */
  static ArrayTermTranslator extract(BlockFormulas blockFormulas, FormulaManagerView fmgr) {
    Map<String, AccessTemplate> found = new LinkedHashMap<>();
    Map<String, Integer> bits = new LinkedHashMap<>();
    Map<String, Integer> arrayBits = new LinkedHashMap<>();
    for (BooleanFormula f : blockFormulas.getFormulas()) {
      String text;
      try {
        text = fmgr.dumpFormula(f).toString();
      } catch (Exception e) {
        continue;
      }
      collectTemplates(text, found);
      collectDeclaredVariables(text, bits);
      collectDeclaredArrays(text, arrayBits);
    }
    return new ArrayTermTranslator(
        ImmutableMap.copyOf(found), ImmutableMap.copyOf(bits), ImmutableMap.copyOf(arrayBits));
  }

  /** Collects declared heap arrays (name -> index bitwidth) from a dumped formula. */
  static void collectDeclaredArrays(String text, Map<String, Integer> arrayIndexBits) {
    Matcher m = DECLARE_ARRAY.matcher(text);
    while (m.find()) {
      String heapName = unversion(m.group(1));
      arrayIndexBits.putIfAbsent(heapName, Integer.parseInt(m.group(2)));
    }
  }

  /** Collects access templates from a dumped-formula text (package-visible for tests). */
  static void collectTemplates(String text, Map<String, AccessTemplate> found) {
    List<Node> roots = Node.parseAll(text);
    Map<String, Node> defs = new HashMap<>();
    for (Node root : roots) {
      root.collectDefs(defs);
    }
    for (Node root : roots) {
      for (Node sel : root.findAll("select")) {
        Optional<AccessTemplate> t = templateForSelect(sel, defs);
        if (t.isPresent()) {
          AccessTemplate tmpl = t.orElseThrow();
          if (!found.containsKey(tmpl.addrSourceName())) {
            found.put(tmpl.addrSourceName(), tmpl);
          }
        }
      }
    }
  }

  /** Collects declared bitvector variables (name -> bitwidth) from a dumped formula. */
  static void collectDeclaredVariables(String text, Map<String, Integer> bits) {
    Matcher m = DECLARE_BV.matcher(text);
    while (m.find()) {
      String unversioned = unversion(m.group(1));
      if (!unversioned.isEmpty()) {
        bits.putIfAbsent(unversioned, Integer.parseInt(m.group(2)));
      }
    }
  }

  /** Whether the predicate text contains a translatable array access. */
  boolean hasArrayAccess(String predicateText) {
    Matcher m = ARRAY_ACCESS.matcher(predicateText);
    while (m.find()) {
      if (templates.containsKey(m.group(1))) {
        return true;
      }
    }
    return false;
  }

  /**
   * Translates {@code (c i)} array accesses to unversioned select terms and rewrites all bare
   * source identifiers to their scoped unversioned names. The result still needs {@link
   * FormulaManagerView#instantiate} with the target head's SSAMap before validation.
   */
  String translate(String predicateText, String functionName) {
    Matcher m = ARRAY_ACCESS.matcher(predicateText);
    StringBuilder out = new StringBuilder();
    int last = 0;
    while (m.find()) {
      AccessTemplate t = templates.get(m.group(1));
      if (t == null) {
        continue;
      }
      out.append(predicateText, last, m.start());
      out.append("(select ");
      out.append(t.heapVar());
      out.append(" (bvadd ").append(t.addrVar());
      out.append(" (bvshl ");
      int idxBits = varBits.getOrDefault(t.idxVar(), 32);
      if (idxBits > 32) {
        // Mirror the CEGAR encoding: narrow the index to 32 bits before the shift.
        out.append("((_ extract 31 0) ").append(t.idxVar()).append(")");
      } else {
        out.append(t.idxVar());
      }
      out.append(" (_ bv").append(t.shiftBits()).append(" 32))))");
      last = m.end();
    }
    if (last == 0) {
      return predicateText;
    }
    out.append(predicateText, last, predicateText.length());
    // Rewrite all remaining bare source identifiers to their scoped unversioned names
    // (e.g. i -> main::i) so the whole predicate can be instantiated with the head SSAMap.
    String result = out.toString();
    // Resolve bare identifiers within the active function scope in ONE pass
    // (precompiled pattern; mapping is function-scoped).
    if (bareIdentifierPattern != null) {
      Map<String, String> activeVars = new HashMap<>();
      String prefix = functionName + "::";
      for (String encoded : varBits.keySet()) {
        if (!encoded.contains("::")) {
          activeVars.put(encoded, encoded);
        } else if (encoded.startsWith(prefix)) {
          activeVars.put(encoded.substring(prefix.length()), encoded);
        }
      }
      if (!activeVars.isEmpty()) {
        Matcher idMatcher = bareIdentifierPattern.matcher(result);
        StringBuilder sb = new StringBuilder();
        while (idMatcher.find()) {
          idMatcher.appendReplacement(
              sb, Matcher.quoteReplacement(activeVars.get(idMatcher.group(1))));
        }
        idMatcher.appendTail(sb);
        result = sb.toString();
      }
    }
    // Fallback: index variables of the translated arrays (works without declare-fun dumps).
    for (AccessTemplate t : templates.values()) {
      String sourceIdx = sourceNameOf(t.idxVar());
      if (!sourceIdx.isEmpty()) {
        result =
            result.replaceAll(
                "(?<![A-Za-z0-9_@|:])" + Pattern.quote(sourceIdx) + "(?![A-Za-z0-9_@|])",
                Matcher.quoteReplacement(t.idxVar()));
      }
    }
    return result;
  }

  /** Unversioned variable bitwidths for the parser's variable creation. */
  Map<String, Integer> varBits() {
    return varBits;
  }

  /** Unversioned heap names and their array types, for the parser's select case. */
  Map<String, FormulaType<?>> arrayTypes() {
    Map<String, FormulaType<?>> types = new LinkedHashMap<>();
    for (AccessTemplate t : templates.values()) {
      int idxBits = arrayIndexBits.getOrDefault(t.heapVar(), 32);
      types.put(
          t.heapVar(),
          FormulaType.getArrayType(
              FormulaType.getBitvectorTypeWithSize(idxBits),
              FormulaType.getBitvectorTypeWithSize(t.elementBits())));
    }
    return types;
  }

  // ---------------------------------------------------------------------------------------------
  // helpers
  // ---------------------------------------------------------------------------------------------

  private static Optional<AccessTemplate> templateForSelect(Node sel, Map<String, Node> defs) {
    // Node children include the operator at index 0: (select HEAP ARG).
    if (sel.children.size() < 3 || !sel.children.get(1).isAtom()) {
      return Optional.empty();
    }
    String heapName = unversion(sel.children.get(1).atom);
    if (!heapName.startsWith("*")) {
      return Optional.empty();
    }
    Node arg = resolve(sel.children.get(2), defs);
    if (!arg.isList("bvadd") || arg.children.size() < 3 || !arg.children.get(1).isAtom()) {
      return Optional.empty();
    }
    String addrName = unversion(arg.children.get(1).atom);
    Node off = resolve(arg.children.get(2), defs);
    Node shiftNode = unwrapExtract(off);
    if (!shiftNode.isList("bvshl") || shiftNode.children.size() < 3) {
      return Optional.empty();
    }
    Node idxNode = unwrapExtract(resolve(shiftNode.children.get(1), defs));
    if (!idxNode.isAtom()) {
      return Optional.empty();
    }
    Integer shift = bvConstantValue(shiftNode.children.get(2));
    if (shift == null || shift < 0 || shift > 12) {
      // Out-of-range shift would overflow the element-size arithmetic below.
      return Optional.empty();
    }
    String idxName = unversion(idxNode.atom);
    int extractMsb = -1;
    int extractLsb = 0;
    ExtractInfo narrowed = unwrapExtractInfo(shiftNode.children.get(1), defs);
    if (narrowed != null) {
      extractMsb = narrowed.extractMsb();
      extractLsb = narrowed.extractLsb();
    }
    Integer shiftConstWidth = bvConstantWidth(shiftNode.children.get(2));
    FormulaType<?> arrayType =
        FormulaType.getArrayType(
            FormulaType.getBitvectorTypeWithSize(32),
            FormulaType.getBitvectorTypeWithSize((1 << shift) * 8));
    return Optional.of(
        new AccessTemplate(
            heapName,
            addrName,
            idxName,
            shift,
            extractMsb,
            extractLsb,
            shiftConstWidth == null ? 32 : shiftConstWidth,
            arrayType));
  }

  /** Returns the extract bounds when {@code n} is an extract wrapper, else null. */
  private static ExtractInfo unwrapExtractInfo(Node n, Map<String, Node> defs) {
    Node cur = resolve(n, defs);
    if (cur.isList("_") && cur.children.size() >= 4 && cur.children.get(1).isAtom()
        && cur.children.get(1).atom.equals("extract")) {
      try {
        return new ExtractInfo(
            Integer.parseInt(cur.children.get(2).atom), Integer.parseInt(cur.children.get(3).atom));
      } catch (NumberFormatException e) {
        return null;
      }
    }
    if (cur.children != null
        && cur.children.size() >= 2
        && cur.children.get(0).isList("_")
        && cur.children.get(0).children.size() >= 4
        && cur.children.get(0).children.get(1).isAtom()
        && cur.children.get(0).children.get(1).atom.equals("extract")) {
      try {
        return new ExtractInfo(
            Integer.parseInt(cur.children.get(0).children.get(2).atom),
            Integer.parseInt(cur.children.get(0).children.get(3).atom));
      } catch (NumberFormatException e) {
        return null;
      }
    }
    return null;
  }

  private record ExtractInfo(int extractMsb, int extractLsb) {}

  private static Integer bvConstantWidth(Node n) {
    if (n.isList("_") && n.children.size() >= 3 && n.children.get(2).isAtom()) {
      try {
        return Integer.parseInt(n.children.get(2).atom);
      } catch (NumberFormatException e) {
        return null;
      }
    }
    return null;
  }

  private static String unversion(String name) {
    // Dump text escapes symbols as |name@N|; the solver's own symbols are bar-less.
    if (name.length() >= 2 && name.startsWith("|") && name.endsWith("|")) {
      name = name.substring(1, name.length() - 1);
    }
    int at = name.lastIndexOf('@');
    return at < 0 ? name : name.substring(0, at);
  }

  private static String sourceNameOf(String unversionedName) {
    String name = unversionedName;
    if (name.length() >= 2 && name.startsWith("|") && name.endsWith("|")) {
      name = name.substring(1, name.length() - 1);
    }
    int scope = name.lastIndexOf("::");
    if (scope >= 0) {
      name = name.substring(scope + 2);
    }
    return name.strip();
  }

  private static Node resolve(Node n, Map<String, Node> defs) {
    Node cur = n;
    for (int i = 0; i < 16; i++) {
      if (cur.isAtom() && cur.atom.startsWith(".def_")) {
        Node next = defs.get(cur.atom);
        if (next == null) {
          return cur;
        }
        cur = next;
      } else {
        return cur;
      }
    }
    return cur;
  }

  /** Unwraps extract wrappers used for 64-to-32-bit index narrowing. */
  private static Node unwrapExtract(Node n) {
    // Flat SMT-LIB form: (_ extract 31 0 VAR) — the variable is the last child.
    if (n.isList("_") && n.children.size() >= 5 && n.children.get(1).isAtom()
        && n.children.get(1).atom.equals("extract")) {
      return n.children.get(4);
    }
    // SMT-LIB writes indexed ops as ((_ extract 31 0) VAR): a nested list + argument.
    if (n.children != null
        && n.children.size() >= 2
        && n.children.get(0).isList("_")
        && n.children.get(0).children.size() >= 2
        && n.children.get(0).children.get(1).isAtom()
        && n.children.get(0).children.get(1).atom.equals("extract")) {
      return n.children.get(1);
    }
    return n;
  }

  private static Integer bvConstantValue(Node n) {
    if (n.isList("_") && n.children.size() >= 2 && n.children.get(1).isAtom()
        && n.children.get(1).atom.startsWith("bv")) {
      try {
        return Integer.parseInt(n.children.get(1).atom.substring(2));
      } catch (NumberFormatException e) {
        return null;
      }
    }
    return null;
  }

  // ---------------------------------------------------------------------------------------------
  // minimal s-expression tree for dumped formulas
  // ---------------------------------------------------------------------------------------------

  private static final class Node {
    final String atom;
    final List<Node> children;

    private Node(String atom, List<Node> children) {
      this.atom = atom;
      this.children = children;
    }

    boolean isAtom() {
      return children == null;
    }

    boolean isList(String op) {
      return children != null && children.size() > 0 && children.get(0).isAtom()
          && children.get(0).atom.equals(op);
    }

    static Node parse(String text) {
      List<Node> all = parseAll(text);
      return all.isEmpty() ? null : all.get(0);
    }

    /** Parses all top-level s-expressions (declares + body) of a dumped formula. */
    static List<Node> parseAll(String text) {
      List<Node> out = new ArrayList<>();
      int[] pos = {0};
      while (true) {
        skipWs(text, pos);
        if (pos[0] >= text.length()) {
          break;
        }
        if (text.charAt(pos[0]) == ')') {
          pos[0]++;
          continue;
        }
        Node n = parseNode(text, pos);
        if (n == null) {
          break;
        }
        out.add(n);
      }
      return out;
    }

    private static Node parseNode(String text, int[] pos) {
      skipWs(text, pos);
      if (pos[0] >= text.length()) {
        return null;
      }
      if (text.charAt(pos[0]) != '(') {
        int start = pos[0];
        if (text.charAt(pos[0]) == '|') {
          // SMT-LIB quoted symbol: |foo bar| — may contain whitespace.
          pos[0]++;
          while (pos[0] < text.length() && text.charAt(pos[0]) != '|') {
            pos[0]++;
          }
          pos[0]++;
        } else {
          while (pos[0] < text.length()
              && !Character.isWhitespace(text.charAt(pos[0]))
              && text.charAt(pos[0]) != ')') {
            pos[0]++;
          }
        }
        return new Node(text.substring(start, pos[0]), null);
      }
      pos[0]++; // consume '('
      List<Node> children = new ArrayList<>();
      while (true) {
        skipWs(text, pos);
        if (pos[0] >= text.length()) {
          return null;
        }
        if (text.charAt(pos[0]) == ')') {
          pos[0]++;
          return new Node(null, children);
        }
        Node child = parseNode(text, pos);
        if (child == null) {
          return null;
        }
        children.add(child);
      }
    }

    private static void skipWs(String text, int[] pos) {
      while (pos[0] < text.length() && Character.isWhitespace(text.charAt(pos[0]))) {
        pos[0]++;
      }
    }

    List<Node> findAll(String op) {
      List<Node> out = new ArrayList<>();
      collect(this, op, out);
      return out;
    }

    private static void collect(Node n, String op, List<Node> out) {
      if (n.isList(op)) {
        out.add(n);
      }
      if (n.children != null) {
        for (Node c : n.children) {
          collect(c, op, out);
        }
      }
    }

    /** Records {@code (let ((.def_N TERM) ...) BODY)} bindings into {@code defs}. */
    void collectDefs(Map<String, Node> defs) {
      collectOwnDefs(defs);
      if (children == null) {
        return;
      }
      for (Node c : children) {
        c.collectDefs(defs);
      }
    }

    private void collectOwnDefs(Map<String, Node> defs) {
      if (isList("let") && children.size() >= 2 && children.get(1).children != null) {
        for (Node binding : children.get(1).children) {
          if (binding.children != null && binding.children.size() >= 2
              && binding.children.get(0).isAtom()) {
            defs.putIfAbsent(binding.children.get(0).atom, binding.children.get(1));
          }
        }
      }
    }
  }
}
