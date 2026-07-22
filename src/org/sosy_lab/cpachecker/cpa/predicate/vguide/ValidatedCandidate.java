// This file is part of CPAchecker,
// a tool for configurable software verification:
// https://cpachecker.sosy-lab.org
//
// SPDX-FileCopyrightText: 2026 SSU-WEI HUANG <https://github.com/swear01>
//
// SPDX-License-Identifier: Apache-2.0

package org.sosy_lab.cpachecker.cpa.predicate.vguide;

import org.sosy_lab.cpachecker.cfa.model.CFANode;
import org.sosy_lab.cpachecker.util.predicates.AbstractionPredicate;

record ValidatedCandidate(
    CandidateProposal proposal, CFANode loopHead, AbstractionPredicate abstractionPredicate) {}
