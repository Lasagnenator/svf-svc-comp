#include <stdbool.h>
#include <stdint.h>
#include <stddef.h>

typedef __int128_t int128;
typedef __loff_t loff_t;
typedef long long longlong;
typedef char* pchar;
typedef uint32_t u32;
typedef unsigned char uchar;
typedef unsigned int uint;
typedef __uint128_t uint128;
typedef unsigned long ulong;
typedef unsigned long long ulonglong;
typedef unsigned short ushort;

#define nondet(X) X __VERIFIER_nondet_##X() { X val; return val; }

nondet(bool)
nondet(char)
nondet(int)
nondet(int128)
nondet(float)
nondet(double)
nondet(loff_t)
nondet(long)
nondet(longlong)
nondet(pchar)
nondet(short)
nondet(size_t)
nondet(u32)
nondet(uchar)
nondet(uint)
nondet(uint128)
nondet(ulong)
nondet(ulonglong)
nondet(unsigned)
nondet(ushort)

extern void svf_assert(bool);
