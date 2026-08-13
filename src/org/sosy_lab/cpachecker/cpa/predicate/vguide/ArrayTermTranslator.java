// This file is part of CPAchecker,
// a tool for configurable software verification:
// https://cpachecker.sosy-lab.org
//
// SPDX-FileCopyrightText: 2007-2024 Dirk Beyer <https://www.sosy-lab.org>
//
// SPDX-License-Identifier: Apache-2.0

package org.sosy_lab.cpachecker.cpa.predicate.vguide;

import com.google.common.collect.ImmutableMap;
import org.checkerframework.checker.nullness.qual.Nullable;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.HashSet;
import java.util.Optional;
import java.util.Set;
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
      Pattern.compile("\\(\\s*([A-Za-z_]\\w*)\\s+([A-Za-z_]\\w*)\\s*\\)");
  private static final Pattern C_ARRAY_ACCESS =
      Pattern.compile("([A-Za-z_]\\w*)\\[([^\\]]+)\\]");
  private static final Pattern CONST_WIDTH_0 = Pattern.compile("\\(_ bv(\\d+) 0\\)");

  /** SMT-LIB keywords/operators that must never be treated as bare identifiers. */
  private static final Set<String> SMT_KEYWORDS =
      Set.of(
          "select", "store", "bvadd", "bvsub", "bvmul", "bvshl", "bvlshr", "bvashr",
          "bvneg", "bvurem", "extract", "and", "or", "not", "=", ">", "<", ">=", "<=",
          "bvslt", "bvsgt", "bvsle", "bvsge", "+", "-", "*", "mod", "_", "bv", "declare-fun");
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
    Set<String> seenKeys = new HashSet<>();
    List<String> keys = new ArrayList<>();
    for (String encoded : varBits.keySet()) {
      if (encoded.isEmpty()) {
        continue;
      }
      String bare = encoded.contains("::") ? encoded.substring(encoded.lastIndexOf("::") + 2) : encoded;
      if (!bare.isEmpty() && !SMT_KEYWORDS.contains(bare) && seenKeys.add(bare)) {
        keys.add(bare);
      }
    }
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
      try {
        collectTemplates(text, found);
        collectDeclaredVariables(text, bits);
        collectDeclaredArrays(text, arrayBits);
      } catch (RuntimeException e) {
        // Malformed dumped formula — skip this block rather than crashing.
      }
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
    Matcher cm = C_ARRAY_ACCESS.matcher(predicateText);
    while (cm.find()) {
      if (templates.containsKey(cm.group(1))) {
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
    if (!hasArrayAccess(predicateText)) {
      // No array reads: leave scalar-only predicates untouched (the parser's
      // resolveVariableName handles them as before).
      return predicateText;
    }
    // Pass 1: C-syntax array reads a[i] (the LLM's preferred form; issue #68).
    String result = translateCSyntax(predicateText, functionName);
    // Pass 2: S-expr array reads (c i) (backward compatible).
    result = translateSexpr(result, functionName);
    // Pass 3: rewrite remaining bare identifiers to their scoped unversioned names
    // (e.g. i -> main::i) so the whole predicate can be instantiated with the head SSAMap.
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
          String replacement = activeVars.get(idMatcher.group(1));
          if (replacement == null) {
            idMatcher.appendReplacement(sb, Matcher.quoteReplacement(idMatcher.group(1)));
          } else {
            idMatcher.appendReplacement(sb, Matcher.quoteReplacement(replacement));
          }
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

  /** Translates {@code a[i]} C-syntax array reads (issue #68). */
  private String translateCSyntax(String predicateText, String functionName) {
    Matcher m = C_ARRAY_ACCESS.matcher(predicateText);
    StringBuilder out = new StringBuilder();
    int last = 0;
    while (m.find()) {
      AccessTemplate t = templates.get(m.group(1));
      if (t == null) {
        continue;
      }
      IndexExpr idx = parseIndexExpr(m.group(2), functionName);
      if (idx == null) {
        continue;
      }
      out.append(predicateText, last, m.start());
      appendSelect(out, t, idx.smt(), idx.width());
      last = m.end();
    }
    if (last == 0) {
      return predicateText;
    }
    out.append(predicateText, last, predicateText.length());
    return out.toString();
  }

  /** Translates {@code (c i)} S-expr array reads (backward compatible). */
  private String translateSexpr(String predicateText, String functionName) {
    Matcher m = ARRAY_ACCESS.matcher(predicateText);
    StringBuilder out = new StringBuilder();
    int last = 0;
    while (m.find()) {
      AccessTemplate t = templates.get(m.group(1));
      if (t == null) {
        continue;
      }
      // The index comes from the CANDIDATE predicate (m.group(2)), scoped to the
      // ACTIVE function (the template may come from a different function); the
      // template's index variable is only used for the narrowing bounds and as a
      // fallback (review #62).
      String candidateIdx = functionName + "::" + m.group(2);
      if (!varBits.containsKey(candidateIdx) && varBits.containsKey(m.group(2))) {
        // The index names a global (unscoped) variable.
        candidateIdx = m.group(2);
      }
      int width = varBits.getOrDefault(candidateIdx, 32);
      out.append(predicateText, last, m.start());
      appendSelect(out, t, candidateIdx, width);
      last = m.end();
    }
    if (last == 0) {
      return predicateText;
    }
    out.append(predicateText, last, predicateText.length());
    return out.toString();
  }

  /** Appends the heap-select term for an array read with the given index SMT. */
  private void appendSelect(
      StringBuilder out, AccessTemplate t, String indexSmt, int indexWidth) {
    out.append("(select ");
    out.append(t.heapVar());
    out.append(" (bvadd ").append(t.addrVar());
    out.append(" (bvshl ");
    if (t.extractMsb() >= 0 && indexWidth > t.extractMsb()) {
      // Mirror the CEGAR encoding: narrow the index exactly as the trace does.
      out.append("((_ extract ")
          .append(t.extractMsb())
          .append(" ")
          .append(t.extractLsb())
          .append(") ")
          .append(indexSmt)
          .append(")");
    } else {
      out.append(indexSmt);
    }
    out.append(" (_ bv")
        .append(t.shiftBits())
        .append(" ")
        .append(t.shiftConstBits())
        .append("))))");
  }

  private record IndexExpr(String smt, int width) {}

  /**
   * Parses a C index expression ({@code i}, {@code 0}, {@code 4*j+1}, ...) into SMT
   * with the width of its first identifier (default 32).
   */
  private @Nullable IndexExpr parseIndexExpr(String expr, String functionName) {
    int[] pos = {0};
    IndexExpr e = parseAddSub(expr, pos, functionName);
    if (e == null) {
      return null;
    }
    // skip trailing whitespace; require full consumption
    while (pos[0] < expr.length() && Character.isWhitespace(expr.charAt(pos[0]))) {
      pos[0]++;
    }
    if (pos[0] != expr.length()) {
      return null;
    }
    // Constant-only expressions have width 0 and default to 32 bits; anything
    // with a variable keeps the variable's actual width (a 16-bit index var
    // must not be forced to 32, which would break the extract bounds).
    int width = e.width() > 0 ? e.width() : 32;
    return new IndexExpr(rewidth(e.smt(), width), width);
  }

  private @Nullable IndexExpr parseAddSub(String expr, int[] pos, String functionName) {
    IndexExpr left = parseMulDiv(expr, pos, functionName);
    if (left == null) {
      return null;
    }
    int width = left.width();
    while (true) {
      skipWs(expr, pos);
      if (pos[0] >= expr.length()) {
        return left;
      }
      char op = expr.charAt(pos[0]);
      if (op != '+' && op != '-') {
        return left;
      }
      pos[0]++;
      IndexExpr right = parseMulDiv(expr, pos, functionName);
      if (right == null) {
        return null;
      }
      width = Math.max(width, right.width());
      // Constants are emitted with width 0; rewidth them to the operand width
      // so both sides of the SMT operation share the same sort (review #69).
      left =
          op == '+'
              ? new IndexExpr(
                  "(bvadd " + rewidth(left.smt(), width) + " " + rewidth(right.smt(), width) + ")",
                  width)
              : new IndexExpr(
                  "(bvsub " + rewidth(left.smt(), width) + " " + rewidth(right.smt(), width) + ")",
                  width);
    }
  }

  private @Nullable IndexExpr parseMulDiv(String expr, int[] pos, String functionName) {
    IndexExpr left = parseFactor(expr, pos, functionName);
    if (left == null) {
      return null;
    }
    int width = left.width();
    while (true) {
      skipWs(expr, pos);
      if (pos[0] >= expr.length()) {
        return left;
      }
      char op = expr.charAt(pos[0]);
      if (op != '*' && op != '/') {
        return left;
      }
      pos[0]++;
      IndexExpr right = parseFactor(expr, pos, functionName);
      if (right == null) {
        return null;
      }
      width = Math.max(width, right.width());
      // C integer division is signed: bvsdiv (review #69).
      left =
          op == '*'
              ? new IndexExpr(
                  "(bvmul " + rewidth(left.smt(), width) + " " + rewidth(right.smt(), width) + ")",
                  width)
              : new IndexExpr(
                  "(bvsdiv " + rewidth(left.smt(), width) + " " + rewidth(right.smt(), width) + ")",
                  width);
    }
  }

  private @Nullable IndexExpr parseFactor(String expr, int[] pos, String functionName) {
    skipWs(expr, pos);
    if (pos[0] >= expr.length()) {
      return null;
    }
    char c = expr.charAt(pos[0]);
    if (c == '(') {
      pos[0]++;
      IndexExpr inner = parseAddSub(expr, pos, functionName);
      if (inner == null) {
        return null;
      }
      skipWs(expr, pos);
      if (pos[0] < expr.length() && expr.charAt(pos[0]) == ')') {
        pos[0]++;
        return inner;
      }
      return null;
    }
    int start = pos[0];
    while (pos[0] < expr.length()
        && (Character.isLetterOrDigit(expr.charAt(pos[0])) || expr.charAt(pos[0]) == '_')) {
      pos[0]++;
    }
    if (start == pos[0]) {
      return null;
    }
    String token = expr.substring(start, pos[0]);
    Long constant = cIntegerLiteral(token);
    if (constant != null) {
      // Width 0 placeholder: rewidthed to the operand width by the caller.
      // toUnsignedString keeps > Long.MAX_VALUE literals positive in SMT.
      return new IndexExpr("(_ bv" + Long.toUnsignedString(constant) + " 0)", 0);
    }
    String scoped = functionName + "::" + token;
    if (!varBits.containsKey(scoped) && varBits.containsKey(token)) {
      scoped = token; // global variable
    }
    int width = varBits.getOrDefault(scoped, 32);
    return new IndexExpr(scoped, width);
  }

  /** Parses a C integer literal (dec/hex, optional u/l/ll suffixes) or null. */
  private static Long cIntegerLiteral(String token) {
    String t = token;
    while (!t.isEmpty() && (t.endsWith("u") || t.endsWith("U") || t.endsWith("l") || t.endsWith("L"))) {
      t = t.substring(0, t.length() - 1);
    }
    try {
      if (t.startsWith("0x") || t.startsWith("0X")) {
        return Long.parseUnsignedLong(t.substring(2), 16);
      }
      return Long.parseUnsignedLong(t);
    } catch (NumberFormatException e) {
      return null;
    }
  }

  /** Rewidths width-0 constants in an index expression to {@code width}. */
  private static String rewidth(String smt, int width) {
    return CONST_WIDTH_0.matcher(smt).replaceAll(mr -> "(_ bv" + mr.group(1) + " " + width + ")");
  }

  private static void skipWs(String expr, int[] pos) {
    while (pos[0] < expr.length() && Character.isWhitespace(expr.charAt(pos[0]))) {
      pos[0]++;
    }
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
    idxNode = resolve(idxNode, defs); // the unwrapped argument may itself be a let-def
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
    try {
      if (cur.isList("_") && cur.children.size() >= 4 && cur.children.get(1).isAtom()
          && cur.children.get(1).atom.equals("extract")
          && cur.children.get(2).isAtom()
          && cur.children.get(3).isAtom()) {
        return new ExtractInfo(
            Integer.parseInt(cur.children.get(2).atom), Integer.parseInt(cur.children.get(3).atom));
      }
      if (cur.children != null
          && cur.children.size() >= 2
          && cur.children.get(0).isList("_")
          && cur.children.get(0).children.size() >= 4
          && cur.children.get(0).children.get(1).isAtom()
          && cur.children.get(0).children.get(1).atom.equals("extract")
          && cur.children.get(0).children.get(2).isAtom()
          && cur.children.get(0).children.get(3).isAtom()) {
        return new ExtractInfo(
            Integer.parseInt(cur.children.get(0).children.get(2).atom),
            Integer.parseInt(cur.children.get(0).children.get(3).atom));
      }
    } catch (RuntimeException e) {
      return null; // malformed extract structure
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
    Set<String> seen = new HashSet<>();
    while (cur.isAtom() && cur.atom.startsWith(".def_")) {
      if (!seen.add(cur.atom)) {
        return cur; // cycle in let-defs — resolve no further
      }
      Node next = defs.get(cur.atom);
      if (next == null) {
        return cur;
      }
      cur = next;
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

    private static final int MAX_PARSE_DEPTH = 512;

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
        Node n = parseNode(text, pos, 0);
        if (n == null) {
          break;
        }
        out.add(n);
      }
      return out;
    }

    private static Node parseNode(String text, int[] pos, int depth) {
      if (depth > MAX_PARSE_DEPTH) {
        return null; // pathologically nested input — treat as unparsable
      }
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
          if (pos[0] >= text.length()) {
            return null; // unterminated quoted symbol
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
        Node child = parseNode(text, pos, depth + 1);
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
