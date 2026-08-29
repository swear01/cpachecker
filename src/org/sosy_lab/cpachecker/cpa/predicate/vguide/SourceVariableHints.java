// This file is part of CPAchecker,
// a tool for configurable software verification:
// https://cpachecker.sosy-lab.org
//
// SPDX-License-Identifier: Apache-2.0

package org.sosy_lab.cpachecker.cpa.predicate.vguide;

import com.google.common.collect.ImmutableList;
import java.util.ArrayList;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Set;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/** Scans C source for variables safe to mention in LLM predicate proposals. */
public final class SourceVariableHints {

  private static final Pattern INT_DECL =
      Pattern.compile(
          "(?m)(?:(?:^|(?<=[;{}]))\\s*|\\bfor\\s*\\(\\s*)"
              + "(?:(?:auto|const|extern|register|restrict|signed|static|unsigned|volatile|long|"
              + "short|_Atomic|_Thread_local)\\s+)*int\\s+"
              + "([^;{}]*(?:=\\s*\\{[^{}]*\\}[^;{}]*)*);");
  private static final Pattern DECLARATOR_NAME =
      Pattern.compile("\\s*([A-Za-z_]\\w*)\\s*(?:=.*)?");
  private static final Pattern ARRAY_NAME =
      Pattern.compile(".*?([A-Za-z_]\\w*)\\s*\\[");

  private SourceVariableHints() {}

  public static ImmutableList<String> scalarNames(String source) {
    Set<String> scalars = new LinkedHashSet<>();
    Set<String> arrays = new LinkedHashSet<>();
    Matcher declaration = INT_DECL.matcher(sourceForScanning(source));
    while (declaration.find()) {
      for (String declarator : splitDeclarators(declaration.group(1))) {
        if (isArrayDeclarator(declarator)) {
          Matcher array = ARRAY_NAME.matcher(declarator);
          if (array.find()) {
            arrays.add(array.group(1));
          }
          continue;
        }
        Matcher name = DECLARATOR_NAME.matcher(declarator);
        if (name.matches()) {
          scalars.add(name.group(1));
        }
      }
    }
    scalars.removeAll(arrays);
    return ImmutableList.copyOf(scalars);
  }

  public static boolean hasArrayDecl(String source) {
    Matcher declaration = INT_DECL.matcher(sourceForScanning(source));
    while (declaration.find()) {
      for (String declarator : splitDeclarators(declaration.group(1))) {
        if (isArrayDeclarator(declarator)) {
          return true;
        }
      }
    }
    return false;
  }

  /** Count scalar int declarations (supports comma-separated names per line). */
  public static int scalarDeclCount(String source) {
    int count = 0;
    Matcher declaration = INT_DECL.matcher(sourceForScanning(source));
    while (declaration.find()) {
      for (String declarator : splitDeclarators(declaration.group(1))) {
        if (isArrayDeclarator(declarator)) {
          continue;
        }
        Matcher name = DECLARATOR_NAME.matcher(declarator);
        if (name.matches()) {
          count++;
        }
      }
    }
    return count;
  }

  public static String formatForPrompt(String source, java.util.Map<String, ?> contract) {
    if (!contract.isEmpty()) {
      return "";
    }
    ImmutableList<String> scalars = scalarNames(source);
    if (scalars.isEmpty()) {
      return "";
    }
    StringBuilder sb = new StringBuilder();
    sb.append("Allowed scalar variables (use ONLY these names): ")
        .append(scalars)
        .append('\n');
    if (hasArrayDecl(source)) {
      sb.append(
          """
          Array program: array element reads are allowed only in source-level C syntax A[i].
          Do not use bare array identifiers, select/store, heap names, or SSA names.
          GOOD: (= A[i] 0), (bvsge i (_ bv0 32)), (bvsle i (_ bv1024 32))
          """);
    }
    return sb.toString();
  }

  private static boolean isArrayDeclarator(String declarator) {
    int initializer = declarator.indexOf('=');
    String declaratorHead = initializer >= 0 ? declarator.substring(0, initializer) : declarator;
    return declaratorHead.contains("[");
  }

  private static String sourceForScanning(String source) {
    return maskStructBodies(maskCommentsAndLiterals(source));
  }

  private static String maskCommentsAndLiterals(String source) {
    StringBuilder masked = new StringBuilder(source);
    for (int i = 0; i < source.length(); ) {
      char current = source.charAt(i);
      if (current == '/' && i + 1 < source.length() && source.charAt(i + 1) == '/') {
        mask(masked, i++);
        mask(masked, i++);
        while (i < source.length() && !isLineBreak(source.charAt(i))) {
          mask(masked, i++);
        }
      } else if (current == '/' && i + 1 < source.length() && source.charAt(i + 1) == '*') {
        mask(masked, i++);
        mask(masked, i++);
        while (i < source.length()) {
          if (source.charAt(i) == '*' && i + 1 < source.length() && source.charAt(i + 1) == '/') {
            mask(masked, i++);
            mask(masked, i++);
            break;
          }
          mask(masked, i++);
        }
      } else if (current == '"' || current == '\'') {
        char quote = current;
        mask(masked, i++);
        boolean escaped = false;
        while (i < source.length()) {
          char character = source.charAt(i);
          mask(masked, i++);
          if (escaped) {
            escaped = false;
          } else if (character == '\\') {
            escaped = true;
          } else if (character == quote) {
            break;
          }
        }
      } else {
        i++;
      }
    }
    return masked.toString();
  }

  private static String maskStructBodies(String source) {
    StringBuilder masked = new StringBuilder(source);
    int structDepth = 0;
    boolean structPending = false;
    int i = 0;
    while (i < source.length()) {
      char current = source.charAt(i);
      if (structDepth > 0) {
        if (current == '{') {
          structDepth++;
        } else if (current == '}') {
          structDepth--;
        } else {
          mask(masked, i);
        }
        i++;
        continue;
      }
      String keyword = null;
      if (isWordAt(source, i, "struct")) {
        keyword = "struct";
      } else if (isWordAt(source, i, "union")) {
        keyword = "union";
      }
      if (keyword != null) {
        structPending = true;
        i += keyword.length();
      } else {
        if (structPending && current == '{') {
          structDepth = 1;
          structPending = false;
        } else if (structPending && current == ';') {
          structPending = false;
        }
        i++;
      }
    }
    return masked.toString();
  }

  private static boolean isWordAt(String source, int offset, String word) {
    if (!source.startsWith(word, offset)) {
      return false;
    }
    return (offset == 0 || !isIdentifierPart(source.charAt(offset - 1)))
        && (offset + word.length() == source.length()
            || !isIdentifierPart(source.charAt(offset + word.length())));
  }

  private static boolean isIdentifierPart(char character) {
    return Character.isLetterOrDigit(character) || character == '_';
  }

  private static boolean isLineBreak(char character) {
    return character == '\n' || character == '\r';
  }

  private static void mask(StringBuilder source, int index) {
    if (!isLineBreak(source.charAt(index))) {
      source.setCharAt(index, ' ');
    }
  }

  private static List<String> splitDeclarators(String declaration) {
    List<String> parts = new ArrayList<>();
    int parenDepth = 0;
    int bracketDepth = 0;
    int braceDepth = 0;
    int start = 0;
    for (int i = 0; i < declaration.length(); i++) {
      char c = declaration.charAt(i);
      switch (c) {
        case '(' -> parenDepth++;
        case ')' -> parenDepth = Math.max(0, parenDepth - 1);
        case '[' -> bracketDepth++;
        case ']' -> bracketDepth = Math.max(0, bracketDepth - 1);
        case '{' -> braceDepth++;
        case '}' -> braceDepth = Math.max(0, braceDepth - 1);
        case ',' -> {
          if (parenDepth == 0 && bracketDepth == 0 && braceDepth == 0) {
            parts.add(declaration.substring(start, i).strip());
            start = i + 1;
          }
        }
        default -> {}
      }
    }
    parts.add(declaration.substring(start).strip());
    return parts;
  }
}
