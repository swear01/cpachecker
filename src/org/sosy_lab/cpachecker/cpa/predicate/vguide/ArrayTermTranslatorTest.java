// This file is part of CPAchecker,
// a tool for configurable software verification:
// https://cpachecker.sosy-lab.org
//
// SPDX-FileCopyrightText: 2007-2024 Dirk Beyer <https://www.sosy-lab.org>
//
// SPDX-License-Identifier: Apache-2.0

package org.sosy_lab.cpachecker.cpa.predicate.vguide;

import static com.google.common.truth.Truth.assertThat;

import java.util.LinkedHashMap;
import java.util.Map;
import java.util.Set;
import org.junit.Test;
import org.sosy_lab.cpachecker.cpa.predicate.VocabularyGuide;
import org.sosy_lab.cpachecker.cpa.predicate.vguide.ArrayTermTranslator.AccessTemplate;
import org.sosy_lab.cpachecker.util.predicates.smt.FormulaManagerView;
import org.sosy_lab.cpachecker.util.predicates.smt.SolverViewBasedTest0;
import org.sosy_lab.java_smt.api.FormulaType;

/** Tests for {@link ArrayTermTranslator} (issue #58/#59/#60). */
public class ArrayTermTranslatorTest extends SolverViewBasedTest0 {

  /** Real ifcomp-shaped dumped formula: let-defs wrap select(+ addr (bvshl idx 3)). */
  private static final String IFCOMP_SHAPED_DUMP =
      "(declare-fun |main::i@6| () (_ BitVec 64)) (declare-fun |main::c@3| () (_ BitVec 32))"
          + " (declare-fun *long_long_int@1 () (Array (_ BitVec 32) (_ BitVec 64)))"
          + " (let ((.def_155 (= |__VERIFIER_assert::cond@2| (_ bv0 32))))"
          + " (let ((.def_147 (bvmul |main::i@6| |main::i@6|)))"
          + " (let ((.def_149 (bvmul |main::i@6| .def_147)))"
          + " (let ((.def_141 ((_ extract 31 0) |main::i@6|)))"
          + " (let ((.def_143 (bvshl .def_141 (_ bv3 32))))"
          + " (let ((.def_144 (bvadd |main::c@3| .def_143)))"
          + " (let ((.def_146 (select *long_long_int@1 .def_144)))"
          + " (let ((.def_150 (= .def_146 .def_149)))"
          + " (and .def_150 .def_155))))))))))";

  private Map<String, AccessTemplate> collect(String text) {
    Map<String, AccessTemplate> found = new LinkedHashMap<>();
    ArrayTermTranslator.collectTemplates(text, found);
    return found;
  }

  @Test
  public void extractsTemplateFromLetDefDump() {
    Map<String, AccessTemplate> found = collect(IFCOMP_SHAPED_DUMP);
    assertThat(found).containsKey("c");
    AccessTemplate t = found.get("c");
    assertThat(t.heapVar()).isEqualTo("*long_long_int");
    assertThat(t.addrVar()).isEqualTo("main::c");
    assertThat(t.idxVar()).isEqualTo("main::i");
    assertThat(t.shiftBits()).isEqualTo(3);
    assertThat(t.elementBits()).isEqualTo(64);
    assertThat(t.arrayType().isArrayType()).isTrue();
    FormulaType.ArrayFormulaType<?, ?> arr =
        (FormulaType.ArrayFormulaType<?, ?>) t.arrayType();
    assertThat(arr.getIndexType()).isEqualTo(FormulaType.getBitvectorTypeWithSize(32));
    assertThat(arr.getElementType()).isEqualTo(FormulaType.getBitvectorTypeWithSize(64));
  }

  @Test
  public void extractsTemplateFromInlineDump() {
    String inline =
        "(= (select *long_long_int@7 (bvadd |main::c@9| (bvshl |main::i@11| (_ bv3 32))))"
            + " (bvmul |main::i@11| (_ bv5 32)))";
    Map<String, AccessTemplate> found = collect(inline);
    assertThat(found).containsKey("c");
    assertThat(found.get("c").heapVar()).isEqualTo("*long_long_int");
    assertThat(found.get("c").addrVar()).isEqualTo("main::c");
    assertThat(found.get("c").idxVar()).isEqualTo("main::i");
  }

  @Test
  public void ignoresNonArraySelects() {
    Map<String, AccessTemplate> found =
        collect("(= (select *long_long_int@1 .def_999) (_ bv0 32))");
    assertThat(found).isEmpty();
  }

  @Test
  public void translatesArrayAccessAndIndexOccurrences() {
    Map<String, AccessTemplate> found = collect(IFCOMP_SHAPED_DUMP);
    Map<String, Integer> bits = new LinkedHashMap<>();
    ArrayTermTranslator.collectDeclaredVariables(IFCOMP_SHAPED_DUMP, bits);
    ArrayTermTranslator translator =
        new ArrayTermTranslator(
            com.google.common.collect.ImmutableMap.copyOf(found),
            com.google.common.collect.ImmutableMap.copyOf(bits));

    assertThat(translator.hasArrayAccess("(= (c i) (bvmul (bvmul i i) i))")).isTrue();
    assertThat(translator.hasArrayAccess("(bvslt i (_ bv10 32))")).isFalse();

    String out = translator.translate("(= (c i) (bvmul (bvmul i i) i))", "main");
    assertThat(out)
        .isEqualTo(
            "(= (select *long_long_int (bvadd main::c (bvshl ((_ extract 31 0) main::i) (_ bv3 32))))"
                + " (bvmul (bvmul main::i main::i) main::i))");
  }

  @Test
  public void noArrayAccessLeavesTextUntouched() {
    Map<String, AccessTemplate> found = collect(IFCOMP_SHAPED_DUMP);
    ArrayTermTranslator translator =
        new ArrayTermTranslator(com.google.common.collect.ImmutableMap.copyOf(found));
    assertThat(translator.translate("(bvslt i (_ bv10 32))", "main"))
        .isEqualTo("(bvslt i (_ bv10 32))");
  }

  @Test
  public void usesCandidateIndexVariableNotTemplateIndex() {
    Map<String, AccessTemplate> found = collect(IFCOMP_SHAPED_DUMP);
    Map<String, Integer> bits = new LinkedHashMap<>();
    ArrayTermTranslator.collectDeclaredVariables(IFCOMP_SHAPED_DUMP, bits);
    bits.put("main::j", 64);
    ArrayTermTranslator translator =
        new ArrayTermTranslator(
            com.google.common.collect.ImmutableMap.copyOf(found),
            com.google.common.collect.ImmutableMap.copyOf(bits));
    // The LLM uses j as the index; the select must use main::j, not the
    // template's main::i (review #62).
    String out = translator.translate("(= (c j) (bvmul j j))", "main");
    assertThat(out)
        .isEqualTo(
            "(= (select *long_long_int (bvadd main::c (bvshl ((_ extract 31 0) main::j) (_ bv3 32))))"
                + " (bvmul main::j main::j))");
  }

  @Test
  public void translatesCSyntaxArrayAccess() {
    Map<String, AccessTemplate> found = collect(IFCOMP_SHAPED_DUMP);
    Map<String, Integer> bits = new LinkedHashMap<>();
    ArrayTermTranslator.collectDeclaredVariables(IFCOMP_SHAPED_DUMP, bits);
    ArrayTermTranslator translator =
        new ArrayTermTranslator(
            com.google.common.collect.ImmutableMap.copyOf(found),
            com.google.common.collect.ImmutableMap.copyOf(bits));

    assertThat(translator.hasArrayAccess("(= c[i] (bvmul (bvmul i i) i))")).isTrue();

    // Simple index: c[i]
    String simple = translator.translate("(= c[i] (bvmul (bvmul i i) i))", "main");
    assertThat(simple)
        .isEqualTo(
            "(= (select *long_long_int (bvadd main::c (bvshl ((_ extract 31 0) main::i) (_ bv3 32))))"
                + " (bvmul (bvmul main::i main::i) main::i))");

    // Arithmetic index: c[4*j+1] (j not declared in the test dump -> 32-bit width)
    String arith = translator.translate("(= c[4*j+1] (bvmul j (_ bv2 64)))", "main");
    assertThat(arith)
        .isEqualTo(
            "(= (select *long_long_int (bvadd main::c (bvshl ((_ extract 31 0)"
                + " (bvadd (bvmul (_ bv4 32) main::j) (_ bv1 32))) (_ bv3 32))))"
                + " (bvmul j (_ bv2 64)))"); // j undeclared in the test dump: only the array index is scoped

    // Hex literal index: c[0x10]
    String hex = translator.translate("(bvsge c[0x10] (_ bv0 64))", "main");
    assertThat(hex)
        .isEqualTo(
            "(bvsge (select *long_long_int (bvadd main::c (bvshl (_ bv16 32) (_ bv3 32))))"
                + " (_ bv0 64))");

    // Constant index: c[0]
    String cnst = translator.translate("(bvsle c[0] (_ bv5 64))", "main");
    assertThat(cnst)
        .isEqualTo(
            "(bvsle (select *long_long_int (bvadd main::c (bvshl (_ bv0 32) (_ bv3 32))))"
                + " (_ bv5 64))");
  }

  @Test
  public void stripsSsaVersionsInArrayCandidates() {
    Map<String, AccessTemplate> found = collect(IFCOMP_SHAPED_DUMP);
    Map<String, Integer> bits = new LinkedHashMap<>();
    ArrayTermTranslator.collectDeclaredVariables(IFCOMP_SHAPED_DUMP, bits);
    bits.put("main::N", 32);
    ArrayTermTranslator translator =
        new ArrayTermTranslator(
            com.google.common.collect.ImmutableMap.copyOf(found),
            com.google.common.collect.ImmutableMap.copyOf(bits));
    // The LLM leaked the SSA version N@2: it must become the scoped unversioned
    // main::N so the head SSAMap instantiation applies the correct version.
    String out = translator.translate("(and (bvslt c[i] N@2) (bvsge i (_ bv0 32)))", "main");
    assertThat(out)
        .isEqualTo(
            "(and (bvslt (select *long_long_int (bvadd main::c (bvshl ((_ extract 31 0) main::i) (_ bv3 32))))"
                + " main::N) (bvsge main::i (_ bv0 32)))");
  }

  @Test
  public void translatedSelectParsesWithSolver() throws Exception {
    Map<String, AccessTemplate> found = collect(IFCOMP_SHAPED_DUMP);
    Map<String, Integer> bits = new LinkedHashMap<>();
    ArrayTermTranslator.collectDeclaredVariables(IFCOMP_SHAPED_DUMP, bits);
    ArrayTermTranslator translator =
        new ArrayTermTranslator(
            com.google.common.collect.ImmutableMap.copyOf(found),
            com.google.common.collect.ImmutableMap.copyOf(bits));
    String translated = translator.translate("(= (c i) (bvmul (bvmul i i) i))", "main");
    assertThat(translated)
        .isEqualTo(
            "(= (select *long_long_int (bvadd main::c (bvshl ((_ extract 31 0) main::i) (_ bv3 32))))"
                + " (bvmul (bvmul main::i main::i) main::i))");
    // Parse with a dedicated CVC4 context: the junit default solver on this machine
    // (MathSAT5/OpenSMT variants) cannot build the array-typed heap variable.
    org.sosy_lab.common.configuration.ConfigurationBuilder cb =
        org.sosy_lab.common.configuration.Configuration.builder();
    cb.setOption("solver.solver", "CVC4");
    org.sosy_lab.cpachecker.util.predicates.smt.Solver solver =
        org.sosy_lab.cpachecker.util.predicates.smt.Solver.create(
            cb.build(),
            org.sosy_lab.common.log.LogManager.createNullLogManager(),
            org.sosy_lab.common.ShutdownNotifier.createDummy());
    FormulaManagerView cvc4 = solver.getFormulaManager();
    var parsed =
        VocabularyGuide.parsePredicate(
            translated, cvc4, Set.of(), translator.arrayTypes(), translator.varBits());
    assertThat(parsed).isNotNull();
  }
}
