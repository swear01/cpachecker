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
      case Z3_WITH_INTERPOLATION ->
          assume()
              .withMessage(
                  "Solver %s segfaults with the bundled Z3 4.5.0 legacy native lib on this"
                      + " machine (see issue #30); disabled until the lib is replaced",
                  solverToUse())
              .that(solverToUse())
              .isNotEqualTo(Solvers.Z3_WITH_INTERPOLATION);
      case Z3 ->
          assume()
              .withMessage(
                  "Solver %s native lib (Z3 4.15.4) requires glibc 2.38, unavailable on this"
                      + " machine (see issue #30); disabled until a compatible lib is installed",
                  solverToUse())
              .that(solverToUse())
              .isNotEqualTo(Solvers.Z3);
      case CVC4 ->
          assume()
              .withMessage(
                  "Solver %s fails the parameterized suite and is not available on all systems"
                      + " (see issue #30)",
                  solverToUse())
              .that(solverToUse())
              .isNotEqualTo(Solvers.CVC4);
      case CVC5 ->
          assume()
              .withMessage(
                  "Solver %s crashes in the shared JVM after other native solvers loaded"
                      + " (see issue #30); disabled until the native libs are fixed",
                  solverToUse())
              .that(solverToUse())
              .isNotEqualTo(Solvers.CVC5);
      // newConfig.setOption("cpa.predicate.createFormulaEncodingEagerly", "false");
      // newConfig.setOption("cpa.predicate.encodeIntegerAs", "BITVECTOR");
      // newConfig.setOption("cpa.predicate.encodeBitvectorAs", "BITVECTOR");
      // newConfig.setOption("cpa.predicate.encodeFloatAs", "INTEGER");
      case BITWUZLA ->
          assume()
              .withMessage(
                  "Solver %s segfaults in Term.toString with the bundled native lib"
                      + " (see issue #30); disabled until the lib is fixed",
                  solverToUse())
              .that(solverToUse())
              .isNotEqualTo(Solvers.BITWUZLA);
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
