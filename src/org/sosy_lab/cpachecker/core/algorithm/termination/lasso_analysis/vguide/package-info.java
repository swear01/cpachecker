// This file is part of CPAchecker,
// a tool for configurable software verification:
// https://cpachecker.sosy-lab.org
//
// SPDX-FileCopyrightText: 2026 Dirk Beyer <https://www.sosy-lab.org>
//
// SPDX-License-Identifier: Apache-2.0

/**
 * VGuide ranking-function hook: an LLM proposes candidate ranking functions (with optional
 * supporting invariants) for loops where LassoRanker's template-based synthesis returns UNKNOWN.
 * Each candidate is verified by a decrease+bounded SMT check before it is accepted, so the LLM
 * acts purely as a verified-candidate provider (Tier S) and can never cause a wrong verdict.
 */
@javax.annotation.ParametersAreNonnullByDefault
@org.sosy_lab.common.annotations.FieldsAreNonnullByDefault
@org.sosy_lab.common.annotations.ReturnValuesAreNonnullByDefault
package org.sosy_lab.cpachecker.core.algorithm.termination.lasso_analysis.vguide;
