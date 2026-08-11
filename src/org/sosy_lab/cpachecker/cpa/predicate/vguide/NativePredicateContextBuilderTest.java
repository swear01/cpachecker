// This file is part of CPAchecker,
// a tool for configurable software verification:
// https://cpachecker.sosy-lab.org
//
// SPDX-License-Identifier: Apache-2.0

package org.sosy_lab.cpachecker.cpa.predicate.vguide;

import static com.google.common.truth.Truth.assertThat;
import static org.sosy_lab.cpachecker.cfa.model.CFANode.newDummyCFANode;

import com.google.common.collect.HashMultimap;
import com.google.common.collect.ImmutableList;
import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.Set;
import org.junit.Test;

/** Native CEGAR predicate context: relevance, provenance split, determinism, caps. */
public class NativePredicateContextBuilderTest {

  private final LoopHeadInfo head = new LoopHeadInfo(newDummyCFANode("f1"), "ignored", "f1");

  private ImmutableList<LoopHeadInfo> loopHeads() {
    return ImmutableList.of(head);
  }

  private static NativePredicateContextBuilder builder(String... llmKeys) {
    Set<String> keys = new HashSet<>(ImmutableList.copyOf(llmKeys));
    return new NativePredicateContextBuilder(keys);
  }

  @Test
  public void includesGlobalsAndRelevantFunctionAndLoopHeadLocals() {
    HashMultimap<String, String> functions = HashMultimap.create();
    functions.put("f1", "(bvslt i n)"); // f1 owns a loop head -> included
    functions.put("helper", "(bvsgt k (_ bv0 32))"); // helper owns none -> excluded
    HashMultimap<String, String> locals = HashMultimap.create();
    locals.put(head.label(), "(= x (_ bv1 32))"); // loop-head local -> included
    locals.put("N999", "(= y (_ bv1 32))"); // not a loop head -> excluded

    var context =
        builder().build(ImmutableList.of("(bvsge i (_ bv0 32))"), functions, locals, loopHeads());

    assertThat(context.entries())
        .containsExactly(
            new NativePredicateContextBuilder.Entry("function f1", "native", "(bvslt i n)", false),
            new NativePredicateContextBuilder.Entry("global", "native", "(bvsge i (_ bv0 32))", false),
            new NativePredicateContextBuilder.Entry(
                "local " + head.label(), "native", "(= x (_ bv1 32))", false))
        .inOrder();
    assertThat(context.omitted()).isEqualTo(0);
  }

  @Test
  public void llmOwnedKeysAreTaggedAsLlmOrigin() {
    HashMultimap<String, String> locals = HashMultimap.create();
    locals.put(head.label(), "(= x (_ bv1 32))");

    var context =
        builder("local " + head.label() + "|(= x (_ bv1 32))")
            .build(ImmutableList.of(), HashMultimap.create(), locals, loopHeads());

    assertThat(context.entries()).hasSize(1);
    assertThat(context.entries().get(0).origin()).isEqualTo("llm");
  }

  @Test
  public void duplicateScopeAndFormulaDeduplicated() {
    HashMultimap<String, String> locals = HashMultimap.create();
    locals.put(head.label(), "(= x (_ bv1 32))");
    locals.put(head.label(), "(= x (_ bv1 32))");

    var context = builder().build(ImmutableList.of(), HashMultimap.create(), locals, loopHeads());

    assertThat(context.entries()).hasSize(1);
  }

  @Test
  public void sortedDeterministicallyByScopeThenSmt() {
    HashMultimap<String, String> locals = HashMultimap.create();
    locals.put(head.label(), "(= z (_ bv2 32))");
    locals.put(head.label(), "(= a (_ bv0 32))");

    var context = builder().build(ImmutableList.of(), HashMultimap.create(), locals, loopHeads());

    assertThat(context.entries().get(0).smt()).isEqualTo("(= a (_ bv0 32))");
    assertThat(context.entries().get(1).smt()).isEqualTo("(= z (_ bv2 32))");
  }

  @Test
  public void predicateCapCountsOmitted() {
    List<String> globals = new ArrayList<>();
    for (int i = 0; i < NativePredicateContextBuilder.MAX_PREDICATES + 5; i++) {
      globals.add("(= x (_ bv" + i + " 32))");
    }

    var context =
        builder().build(globals, HashMultimap.create(), HashMultimap.create(), loopHeads());

    assertThat(context.entries()).hasSize(NativePredicateContextBuilder.MAX_PREDICATES);
    assertThat(context.omitted()).isEqualTo(5);
  }

  @Test
  public void sameInputProducesSameContextAndFormat() {
    HashMultimap<String, String> locals = HashMultimap.create();
    locals.put(head.label(), "(= x (_ bv1 32))");

    var a =
        builder()
            .build(ImmutableList.of("(bvsge i (_ bv0 32))"), HashMultimap.create(), locals, loopHeads());
    var b =
        builder()
            .build(ImmutableList.of("(bvsge i (_ bv0 32))"), HashMultimap.create(), locals, loopHeads());

    assertThat(a).isEqualTo(b);
    assertThat(NativePredicateContextBuilder.format(a))
        .isEqualTo(NativePredicateContextBuilder.format(b));
    assertThat(NativePredicateContextBuilder.format(a))
        .contains("[global | native] (bvsge i (_ bv0 32))");
  }

  @Test
  public void tighterConstantBoundSubsumesLooserOne() {
    HashMultimap<String, String> locals = HashMultimap.create();
    locals.put(head.label(), "(bvsge x (_ bv5 32))");
    locals.put(head.label(), "(bvsge x (_ bv0 32))");

    var context = builder().build(List.of(), HashMultimap.create(), locals, loopHeads());

    assertThat(context.entries()).hasSize(2);
    // sorted by smt: (bvsge x 0) first, (bvsge x 5) second; x>=5 subsumes x>=0.
    assertThat(context.entries().get(0).subsumed()).isTrue();
    assertThat(context.entries().get(1).subsumed()).isFalse();
  }

  @Test
  public void conjunctionAtomSubsumptionIsMarked() {
    HashMultimap<String, String> locals = HashMultimap.create();
    locals.put(head.label(), "(and (= x (_ bv1 32)) (= y (_ bv2 32)))");
    locals.put(head.label(), "(= y (_ bv2 32))");

    var context = builder().build(List.of(), HashMultimap.create(), locals, loopHeads());

    assertThat(context.entries()).hasSize(2);
    boolean conjunctionSubsumes =
        context.entries().get(0).smt().startsWith("(and ")
            ? context.entries().get(1).subsumed()
            : context.entries().get(0).subsumed();
    assertThat(conjunctionSubsumes).isTrue();
  }

  @Test
  public void oppositeDirectionBoundsAreNotSubsumed() {
    HashMultimap<String, String> locals = HashMultimap.create();
    locals.put(head.label(), "(bvsge x (_ bv0 32))");
    locals.put(head.label(), "(bvsle x (_ bv0 32))");

    var context = builder().build(List.of(), HashMultimap.create(), locals, loopHeads());

    assertThat(context.entries()).hasSize(2);
    assertThat(context.entries().get(0).subsumed()).isFalse();
    assertThat(context.entries().get(1).subsumed()).isFalse();
  }

  @Test
  public void selectionRuleIsRecorded() {
    var context =
        builder().build(ImmutableList.of(), HashMultimap.create(), HashMultimap.create(), loopHeads());
    assertThat(context.selectionRule()).contains("loop-head");
  }
}
