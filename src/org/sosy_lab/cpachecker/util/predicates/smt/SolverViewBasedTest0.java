// This file is part of CPAchecker,
// a tool for configurable software verification:
// https://cpachecker.sosy-lab.org
//
// SPDX-FileCopyrightText: 2007-2020 Dirk Beyer <https://www.sosy-lab.org>
//
// SPDX-License-Identifier: Apache-2.0

package org.sosy_lab.cpachecker.util.predicates.smt;

import static com.google.common.truth.TruthJUnit.assume;

import edu.umd.cs.findbugs.annotations.SuppressFBWarnings;
import org.junit.After;
import org.junit.Before;
import org.sosy_lab.common.configuration.ConfigurationBuilder;
import org.sosy_lab.common.configuration.InvalidConfigurationException;
import org.sosy_lab.java_smt.SolverContextFactory.Solvers;
import org.sosy_lab.java_smt.test.SolverBasedTest0;

/**
 * Abstract base class for tests that use an SMT solver just like {@link SolverBasedTest0}, but
 * additionally providing {@link Solver} and {@link FormulaManagerView} instances.
 */
@SuppressFBWarnings(value = "NP_NONNULL_FIELD_NOT_INITIALIZED_IN_CONSTRUCTOR")
public class SolverViewBasedTest0 extends SolverBasedTest0 {

  protected Solver solver;
  protected FormulaManagerView mgrv;
  protected BooleanFormulaManagerView bmgrv;
  protected IntegerFormulaManagerView imgrv;

  /**
   * Machine-gated exclusion for native solvers broken in this environment (issue #30).
   * Other machines keep full solver coverage unless they opt in via
   * {@code VGUIDE_SKIP_BROKEN_NATIVE_SOLVERS=1}.
   */
  private static boolean skipBrokenNativeSolvers() {
    String value = System.getenv("VGUIDE_SKIP_BROKEN_NATIVE_SOLVERS");
    return "1".equals(value) || "true".equalsIgnoreCase(value);
  }

  private void assumeNotBrokenNative(Solvers solver, String reason) {
    if (skipBrokenNativeSolvers()) {
      assume()
          .withMessage("Solver %s disabled: %s (issue #30)", solver, reason)
          .that(solverToUse())
          .isNotEqualTo(solver);
    }
  }

  @Override
  protected ConfigurationBuilder createTestConfigBuilder() {
    ConfigurationBuilder newConfig = super.createTestConfigBuilder();

    // Automatically choose theories that are supported by the solver.
    // With unsupported theories, test would just fail.
    // We could also use the same theory (QF_AUFLIA) for all solvers,
    // but maybe testing a set of several theories is not bad after all.
    switch (solverToUse()) {
      case SMTINTERPOL -> {
        newConfig.setOption("cpa.predicate.encodeBitvectorAs", "INTEGER");
        newConfig.setOption("cpa.predicate.encodeFloatAs", "RATIONAL");
      }
      case PRINCESS -> {
        newConfig.setOption("cpa.predicate.encodeBitvectorAs", "INTEGER");
        newConfig.setOption("cpa.predicate.encodeFloatAs", "INTEGER");
      }
      case BOOLECTOR ->
          assume()
              .withMessage("Solver %s does not support the tested features", solverToUse())
              .that(solverToUse())
              .isNotEqualTo(Solvers.BOOLECTOR);
      case Z3 -> assumeNotBrokenNative(
          Solvers.Z3, "bundled libz3.so requires glibc 2.38, unavailable on this machine");
      case Z3_WITH_INTERPOLATION -> assumeNotBrokenNative(
          Solvers.Z3_WITH_INTERPOLATION, "bundled Z3 4.5.0 legacy lib segfaults");
      case CVC4 -> assumeNotBrokenNative(
          Solvers.CVC4, "fails in the shared-JVM parameterized runs");
      case CVC5 -> assumeNotBrokenNative(
          Solvers.CVC5, "crashes in the shared-JVM parameterized runs");
      case BITWUZLA -> assumeNotBrokenNative(
          Solvers.BITWUZLA, "BitwuzlaNativeJNI.Term_toString segfaults in libstdc++");
      // newConfig.setOption("cpa.predicate.createFormulaEncodingEagerly", "false");
      // newConfig.setOption("cpa.predicate.encodeIntegerAs", "BITVECTOR");
      // newConfig.setOption("cpa.predicate.encodeBitvectorAs", "BITVECTOR");
      // newConfig.setOption("cpa.predicate.encodeFloatAs", "INTEGER");
      case OPENSMT -> {
        newConfig.setOption("cpa.predicate.encodeBitvectorAs", "INTEGER");
        newConfig.setOption("cpa.predicate.encodeFloatAs", "INTEGER");
      }
      case YICES2 ->
          assume()
              .withMessage(
                  "Solver %s is not available on all systems, disabling it for CPAchecker",
                  solverToUse())
              .that(solverToUse())
              .isNotEqualTo(Solvers.YICES2);
      default -> {
        newConfig.setOption("cpa.predicate.encodeBitvectorAs", "BITVECTOR");
        newConfig.setOption("cpa.predicate.encodeFloatAs", "FLOAT");
      }
    }
    return newConfig;
  }

  @Before
  public final void initCPAcheckerSolver() throws InvalidConfigurationException {
    solver = new Solver(factory, solverToUse(), context, config, logger);
    mgrv = solver.getFormulaManager();
    bmgrv = mgrv.getBooleanFormulaManager();
    imgrv = mgrv.getIntegerFormulaManager();
  }

  @After
  public final void closeCPAcheckerSolver() {
    // We should close the solver, but the super class does this, too,
    // and calling it twice can segfault.
    // solver.close();
  }
}
