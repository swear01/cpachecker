// This file is part of CPAchecker,
// a tool for configurable software verification:
// https://cpachecker.sosy-lab.org
//
// SPDX-License-Identifier: Apache-2.0

package org.sosy_lab.cpachecker.cpa.predicate.vguide;

import com.google.common.collect.ImmutableList;
import com.google.common.collect.ImmutableMap;
import com.google.common.collect.ImmutableSet;
import java.util.List;
import org.sosy_lab.cpachecker.cpa.predicate.BlockFormulaStrategy.BlockFormulas;
import org.sosy_lab.java_smt.api.BooleanFormula;

/** Immutable context for one VGuide LLM round. */
public record ContextPack(
    int refinementIndex,
    String sourceCode,
    String assertion,
    ImmutableList<LoopHeadInfo> loopHeads,
    ImmutableMap<String, ImmutableSet<String>> varContract,
    ImmutableSet<String> encodedVars,
    BlockFormulas blockFormulas,
    ImmutableList<BooleanFormula> interpolants,
    String traceSummary) {}
