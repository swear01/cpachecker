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
import java.util.HashSet;
import java.util.List;
import java.util.Set;
import org.junit.Test;

/**
 * Isolation of the native-predicate context state (issue #35): llmOwnedKeys and the context
 * builder are per-bridge instances, so restarts, precision updates and nested analyses must never
 * leak state across bridges.
 */
public class NativePredicateContextIsolationTest {

  private static final LoopHeadInfo HEAD =
      new LoopHeadInfo(newDummyCFANode("f1"), "ignored", "f1");

  private static final String KEY = "local " + HEAD.label() + "|(= x (_ bv1 32))";

  private static HashMultimap<String, String> locals() {
    HashMultimap<String, String> locals = HashMultimap.create();
    locals.put(HEAD.label(), "(= x (_ bv1 32))");
    return locals;
  }

  private static ImmutableList<LoopHeadInfo> loopHeads() {
    return ImmutableList.of(HEAD);
  }

  @Test
  public void newBridgeStartsWithEmptyOwnershipKeys() {
    // A fresh bridge owns no keys, even though the previous one accumulated some.
    Set<String> freshKeys = new HashSet<>();
    NativePredicateContextBuilder fresh = new NativePredicateContextBuilder(freshKeys);

    var context = fresh.build(List.of(), HashMultimap.create(), locals(), loopHeads());

    assertThat(freshKeys).isEmpty();
    // Without ownership keys the same local predicate is tagged native, not llm.
    assertThat(context.entries()).hasSize(1);
    assertThat(context.entries().get(0).origin()).isEqualTo("native");
  }

  @Test
  public void ownershipKeysDoNotLeakAcrossBuilders() {
    Set<String> keysA = new HashSet<>(List.of(KEY));
    Set<String> keysB = new HashSet<>();
    NativePredicateContextBuilder a = new NativePredicateContextBuilder(keysA);
    NativePredicateContextBuilder b = new NativePredicateContextBuilder(keysB);

    var contextA = a.build(List.of(), HashMultimap.create(), locals(), loopHeads());
    var contextB = b.build(List.of(), HashMultimap.create(), locals(), loopHeads());

    assertThat(contextA.entries().get(0).origin()).isEqualTo("llm");
    assertThat(contextB.entries().get(0).origin()).isEqualTo("native");
  }

  @Test
  public void builderNeverMutatesTheOwnershipKeySet() {
    Set<String> keys = new HashSet<>(List.of(KEY));
    NativePredicateContextBuilder builder = new NativePredicateContextBuilder(keys);

    builder.build(List.of(), HashMultimap.create(), locals(), loopHeads());

    // Building context must not add or remove ownership keys (read-only view).
    assertThat(keys).containsExactly(KEY);
  }

  @Test
  public void deterministicContextAcrossIndependentBridges() {
    // Two bridges with identical inputs (same keys, same precision) produce identical context.
    var a =
        new NativePredicateContextBuilder(new HashSet<>(List.of(KEY)))
            .build(List.of(), HashMultimap.create(), locals(), loopHeads());
    var b =
        new NativePredicateContextBuilder(new HashSet<>(List.of(KEY)))
            .build(List.of(), HashMultimap.create(), locals(), loopHeads());

    assertThat(a).isEqualTo(b);
  }
}
