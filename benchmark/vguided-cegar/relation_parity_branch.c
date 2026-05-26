extern void abort(void);
extern void __assert_fail(const char *, const char *, unsigned int, const char *) __attribute__ ((__nothrow__ , __leaf__)) __attribute__ ((__noreturn__));
void reach_error() { __assert_fail("0", "relation_parity_branch.c", 3, "reach_error"); }
extern int __VERIFIER_nondet_int(void);

void __VERIFIER_assert(int cond) {
  if (!(cond)) {
    ERROR: {reach_error();abort();}
  }
  return;
}

int main(void) {
  int x = 0;
  int y = 0;
  int n = __VERIFIER_nondet_int();
  int mode = __VERIFIER_nondet_int();

  while (n > 0) {
    if (mode % 2 == 0) {
      x += 2;
      y += 2;
    } else {
      x++;
      y++;
    }
    n--;
  }

  __VERIFIER_assert((x % 2) == (y % 2));
  return 0;
}
