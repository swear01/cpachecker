extern void abort(void);
extern void __assert_fail(const char *, const char *, unsigned int, const char *) __attribute__ ((__nothrow__ , __leaf__)) __attribute__ ((__noreturn__));
void reach_error() { __assert_fail("0", "relation_asymmetric.c", 3, "reach_error"); }
extern int __VERIFIER_nondet_int(void);

void __VERIFIER_assert(int cond) {
  if (!(cond)) {
    ERROR: {reach_error();abort();}
  }
  return;
}

int main(void) {
  int x = 0;
  int y = __VERIFIER_nondet_int();
  int n = __VERIFIER_nondet_int();

  while (n > 0) {
    if (x % 2 == 0) {
      x += 2;
    } else {
      x++;
    }
    n--;
  }

  __VERIFIER_assert((x % 2) == (y % 2));
  return 0;
}
