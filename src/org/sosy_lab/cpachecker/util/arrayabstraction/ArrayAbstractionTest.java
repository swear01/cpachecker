// This file is part of CPAchecker,
// a tool for configurable software verification:
// https://cpachecker.sosy-lab.org
//
// SPDX-FileCopyrightText: 2026 Dirk Beyer <https://www.sosy-lab.org>
//
// SPDX-License-Identifier: Apache-2.0

package org.sosy_lab.cpachecker.util.arrayabstraction;

import static com.google.common.truth.Truth.assertThat;

import org.junit.Test;
import org.sosy_lab.common.ShutdownNotifier;
import org.sosy_lab.common.configuration.Configuration;
import org.sosy_lab.common.log.LogManager;
import org.sosy_lab.cpachecker.cfa.CFACreator;
import org.sosy_lab.cpachecker.cfa.ast.c.CBinaryExpression;
import org.sosy_lab.cpachecker.cfa.model.c.CAssumeEdge;
import org.sosy_lab.cpachecker.cfa.model.c.CStatementEdge;
import org.sosy_lab.cpachecker.cfa.types.c.CNumericTypes;

public class ArrayAbstractionTest {
  private ArrayAbstractionResult transform(String source) throws Exception {
    var config =
        Configuration.builder()
            .setOption("analysis.machineModel", "Linux32")
            .setOption("cfa.export", "false")
            .setOption("cfa.exportPerFunction", "false")
            .setOption("cfa.callgraph.export", "false")
            .build();
    var logger = LogManager.createTestLogManager();
    var cfa =
        new CFACreator(config, logger, ShutdownNotifier.createDummy())
            .parseSourceAndCreateCFA(source);
    return ArrayAbstraction.transformCfa(config, logger, cfa);
  }

  private String doubleWriteProgram(String bound, String mutation) {
    return "extern void abort(void); extern void error(void); void check(int"
        + " x){if(x<0){error();abort();}} int main(void) { int N=100; int a[202]; int i;"
        + "for(i=0;i<=100;i++){a[2*i]=0;a[2*i+1]=0;}for(i=0;i<="
        + bound
        + ";i++){check(a[i]);"
        + mutation
        + "} return 0;}";
  }

  @Test
  public void preservesBothWritesInRetainedInitializationLoop() throws Exception {
    var result = transform(doubleWriteProgram("200", ""));
    assertThat(result.getStatus()).isEqualTo(ArrayAbstractionResult.Status.PRECISE);
    assertThat(result.getTransformedLoops()).hasSize(1);
    assertThat(result.getTransformedCfa().getLoopStructure().orElseThrow().getAllLoops())
        .hasSize(1);
    assertThat(
            result.getTransformedCfa().nodes().stream()
                .flatMap(node -> node.getAllLeavingEdges().stream())
                .filter(CStatementEdge.class::isInstance)
                .map(CStatementEdge.class::cast)
                .filter(edge -> edge.getStatement().toASTString().equals("__array_value_a = 0;"))
                .count())
        .isEqualTo(2);
  }

  @Test
  public void promotesNarrowSubscriptBeforeComparingTrackedIndex() throws Exception {
    var result =
        transform(doubleWriteProgram("200", "").replace("a[2*i]", "a[(unsigned char)(2*i)]"));
    assertThat(result.getStatus()).isEqualTo(ArrayAbstractionResult.Status.PRECISE);
    var guards =
        result.getTransformedCfa().edges().stream()
            .filter(CAssumeEdge.class::isInstance)
            .map(CAssumeEdge.class::cast)
            .map(CAssumeEdge::getExpression)
            .filter(CBinaryExpression.class::isInstance)
            .map(CBinaryExpression.class::cast)
            .filter(
                expression ->
                    expression.toASTString().contains("unsigned char")
                        && expression.toASTString().contains("__array_index_a"))
            .toList();
    assertThat(guards).hasSize(2);
    for (var guard : guards) {
      assertThat(guard.getCalculationType().getCanonicalType())
          .isEqualTo(CNumericTypes.INT.getCanonicalType());
    }
  }

  @Test
  public void recognizesUnchangedLocalBound() throws Exception {
    var result = transform(doubleWriteProgram("2*N", ""));
    assertThat(result.getStatus()).isEqualTo(ArrayAbstractionResult.Status.PRECISE);
    assertThat(result.getTransformedLoops()).hasSize(1);
  }

  @Test
  public void doesNotFreezeChangingOrAddressedBounds() throws Exception {
    for (String mutation : new String[] {"N--;", "check((int)&N);"}) {
      assertThat(transform(doubleWriteProgram("2*N", mutation)).getStatus())
          .isEqualTo(ArrayAbstractionResult.Status.UNCHANGED);
    }
    for (String declaration : new String[] {"volatile int N=100", "static int N=100"}) {
      assertThat(
              transform(doubleWriteProgram("2*N", "").replace("int N=100", declaration))
                  .getStatus())
          .isEqualTo(ArrayAbstractionResult.Status.UNCHANGED);
    }
  }

  @Test
  public void doesNotChangeComparisonSignedness() throws Exception {
    assertThat(
            transform(doubleWriteProgram("2*N", "").replace("int N=100", "unsigned int N=100"))
                .getStatus())
        .isEqualTo(ArrayAbstractionResult.Status.UNCHANGED);
  }

  @Test
  public void preservesNarrowingOfLocalBound() throws Exception {
    var result =
        transform(doubleWriteProgram("2*N", "").replace("int N=100", "unsigned char N=260"));
    assertThat(result.getStatus()).isEqualTo(ArrayAbstractionResult.Status.PRECISE);
    assertThat(result.getTransformedLoops()).hasSize(1);
    assertThat(
            result
                .getTransformedLoops()
                .iterator()
                .next()
                .getIndex()
                .getComparisonOperation()
                .getValue())
        .isEqualTo(java.math.BigInteger.valueOf(8));
  }

  @Test
  public void preservesExistingSingleIndexTransformation() throws Exception {
    var result =
        transform(
            "extern void abort(void); extern void error(void); void check(int"
                + " x){if(x<0){error();abort();}} int main(void){int a[4];int"
                + " i;for(i=0;i<4;i++)a[i]=0;for(i=0;i<4;i++)check(a[i]);return 0;}");
    assertThat(result.getStatus()).isEqualTo(ArrayAbstractionResult.Status.PRECISE);
    assertThat(result.getTransformedLoops()).hasSize(2);
    assertThat(result.getTransformedCfa().getLoopStructure().orElseThrow().getAllLoops()).isEmpty();
  }

  private String globalBoundProgram(String declaration, String before, String body) {
    return "extern void abort(void); extern int __VERIFIER_nondet_int(void); "
        + "void check(int v){if(v<0)abort();}"
        + declaration
        + "; int main(void){int a[100];int i;"
        + before
        + "for(i=0;i<N;i++){a[i]=__VERIFIER_nondet_int();"
        + body
        + "}for(i=0;i<N;i++){check(a[i]);}return 0;}";
  }

  @Test
  public void recognizesUnchangedGlobalBound() throws Exception {
    var result = transform(globalBoundProgram("int N=100", "", ""));
    assertThat(result.getStatus()).isEqualTo(ArrayAbstractionResult.Status.PRECISE);
    assertThat(result.getTransformedLoops()).hasSize(2);
  }

  @Test
  public void doesNotFreezeMutableGlobalBounds() throws Exception {
    for (String source :
        new String[] {
          globalBoundProgram("int N=100", "N=50;", ""),
          globalBoundProgram("int N=100", "", "N--;"),
          globalBoundProgram("int N=100;void change(void){N=50;}", "change();", ""),
          globalBoundProgram("int N=100;void change(void){N=50;}", "", "change();"),
          globalBoundProgram("int N=100", "int *p=&N;*p=50;", ""),
          globalBoundProgram("volatile int N=100", "", ""),
          globalBoundProgram("int N=100;extern void change(void)", "change();", ""),
          globalBoundProgram("int N=100;extern void change(void)", "", "change();")
        }) {
      assertThat(transform(source).getStatus()).isEqualTo(ArrayAbstractionResult.Status.UNCHANGED);
    }
  }

  @Test
  public void preservesNarrowingOfGlobalBound() throws Exception {
    var result = transform(globalBoundProgram("unsigned char N=260", "", ""));
    assertThat(result.getStatus()).isEqualTo(ArrayAbstractionResult.Status.PRECISE);
    assertThat(result.getTransformedLoops()).hasSize(2);
    for (var loop : result.getTransformedLoops()) {
      assertThat(loop.getIndex().getComparisonOperation().getValue())
          .isEqualTo(java.math.BigInteger.valueOf(3));
    }
  }

  @Test
  public void doesNotWrapStrictComparisonBounds() throws Exception {
    assertThat(transform(globalBoundProgram("int N=(-2147483647-1)", "", "")).getStatus())
        .isEqualTo(ArrayAbstractionResult.Status.UNCHANGED);
    assertThat(
            transform(globalBoundProgram("int N=2147483647", "", "").replace("i<N;i++", "i>N;i--"))
                .getStatus())
        .isEqualTo(ArrayAbstractionResult.Status.UNCHANGED);
  }
}
