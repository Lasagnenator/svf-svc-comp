/*
 * Definitions for the __VERIFIER_* functions SV-COMP tasks declare but do not define.
 * Most are weak, so a task's own definition wins. Each ends the run with an exit
 * code that tells concrete_run.py what happened:
 *
 *   REACHED_ERROR  reach_error (or __VERIFIER_error) was entered: a real violation.
 *   NONDET_CALLED  the program asked for a nondet value, which is not modelled yet:
 *                  no verdict.
 *   0              a __VERIFIER_assume failed: the path ends without a violation.
 *
 * REACHED_ERROR and NONDET_CALLED are passed in with -D by concrete_run.py
 */

#include <stdio.h>
#include <stdlib.h>
#include <unistd.h>

#if !defined(REACHED_ERROR) || !defined(NONDET_CALLED)
#error "Build through concrete_run.py, which passes -DREACHED_ERROR and -DNONDET_CALLED"
#endif

/* The task is built with -finstrument-functions. The stubs must not be instrumented,
 * or the entry hook below would call itself. */
#define NI __attribute__((no_instrument_function))

/* Record where reach_error was called from (addr2line turns it into the witness line),
 * then stop. The file name comes from the CONCRETE_SITE environment variable. */
NI static void reached(void *call_site) {
    FILE *f = fopen(getenv("CONCRETE_SITE"), "w");
    if (f) {
        fprintf(f, "%p\n", call_site);
        fclose(f);
    }
    _exit(REACHED_ERROR);
}

/*
 * Catching reach_error takes two parts, because most tasks define it themselves
 * (usually as a call to __assert_fail) and some only declare it:
 *
 *  - Declared only: these weak definitions are used, and call reached() directly.
 *  - Defined by the task: its definition wins over the weak one, so instead the
 *    -finstrument-functions hook below sees the call on entry.
 */
NI __attribute__((weak)) void reach_error(void) { reached(__builtin_return_address(0)); }
NI __attribute__((weak)) void __VERIFIER_error(void) { reached(__builtin_return_address(0)); }

/* gcc calls this on entry to every instrumented function. */
NI void __cyg_profile_func_enter(void *fn, void *call_site) {
    if (fn == (void *)reach_error || fn == (void *)__VERIFIER_error)
        reached(call_site);
}
NI void __cyg_profile_func_exit(void *fn, void *call_site) {}

/*
 * Nondet values are not modelled: the first request for one stops the run with no
 * verdict. So any violation a run does show lies on the task's one input-free path,
 * and its witness needs no waypoints.
 *
 * Weak, in case a task defines some of these itself.
 *
 * For example, NONDET(int, int) defines int __VERIFIER_nondet_int(void), which exits
 * with NONDET_CALLED.
 */
#define NONDET(type, name) \
    NI __attribute__((weak)) type __VERIFIER_nondet_##name(void) { _exit(NONDET_CALLED); }

NONDET(_Bool, bool)
NONDET(_Bool, _Bool)
NONDET(char, char)
NONDET(unsigned char, uchar)
NONDET(unsigned char, unsigned_char)
NONDET(short, short)
NONDET(unsigned short, ushort)
NONDET(int, int)
NONDET(unsigned int, uint)
NONDET(unsigned int, unsigned)
NONDET(long, long)
NONDET(unsigned long, ulong)
NONDET(unsigned long, size_t)
NONDET(long long, longlong)
NONDET(unsigned long long, ulonglong)
NONDET(float, float)
NONDET(double, double)
NONDET(long double, longdouble)
NONDET(void *, pointer)
NONDET(char *, charp)

/* A failed assumption means the path is not a real execution: end it cleanly. */
NI __attribute__((weak)) void __VERIFIER_assume(int cond) {
    if (!cond)
        _exit(0);
}
