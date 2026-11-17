import json
import math
import operator
import random
import struct
from fractions import Fraction
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
DRIVER = """
import json, sys
from pathlib import Path
import pysvf
from AbstractInterpretation import AbstractExecution
pysvf.buildSVFModule([sys.argv[2]])
analysis = AbstractExecution(pysvf.getPAG())
if sys.argv[4] == 'exact':
    from violations import definite_reach_segments
    status = {}
    segments = definite_reach_segments(analysis, analysis.svfir, sys.argv[1],
                                      len(Path(sys.argv[1]).read_text().splitlines()), sys.argv[3], proof_status=status)
    result = {'violation': bool(segments), 'safe': status.get('safe', False)}
else:
    result = analysis.refineReachability(sys.argv[1], len(Path(sys.argv[1]).read_text().splitlines()), sys.argv[3], 2.0)
print('PROOF_RESULT=' + json.dumps(result))
pysvf.releasePAG()
"""


class SymbolicInductionTests(unittest.TestCase):
    def run_program(self, source, bits='64', mode='primary'):
        with tempfile.TemporaryDirectory(prefix='svf-proof-extension-') as directory:
            original = Path(directory) / 'control.c'
            llvm = Path(directory) / 'control.ll'
            original.write_text(source)
            compiled = subprocess.run(
                ['clang-21', '-m' + bits, '-O0', '-g', '-fno-discard-value-names',
                 '-fgnu89-inline', '-S', '-emit-llvm', str(original), '-o', str(llvm)],
                capture_output=True, text=True, timeout=20,
            )
            self.assertEqual(compiled.returncode, 0, compiled.stderr)
            command = [sys.executable, '-c', DRIVER, str(original), str(llvm), bits, mode]
            if mode == 'driver':
                command = [sys.executable, str(ROOT / 'svf_run.py'), str(original), '--bits', bits,
                           '--prop', str(ROOT / 'tests/unreach-call.prp'), '--witness', str(Path(directory) / 'witness.yml')]
            completed = subprocess.run(
                command,
                cwd=ROOT, capture_output=True, text=True, timeout=20,
            )
            self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
            if mode == 'driver':
                verdicts = [line for line in completed.stdout.splitlines() if line in ('REACH Correct', 'REACH Incorrect', 'Unknown')]
                self.assertEqual(len(verdicts), 1, completed.stdout + completed.stderr)
                return {'verdict': verdicts[0], 'witness': (Path(directory) / 'witness.yml').exists()}
            records = [line.removeprefix('PROOF_RESULT=') for line in completed.stdout.splitlines()
                       if line.startswith('PROOF_RESULT=')]
            self.assertEqual(len(records), 1, completed.stdout)
            return json.loads(records[0])

    def test_return_phi_uses_completed_value(self):
        prefix = '''extern void reach_error(void);
extern int __VERIFIER_nondet_int(void);
_Bool choose(int value) { return value>0 && value<2; }
'''
        for bits in ('32', '64'):
            for unsafe in (False, True):
                for mode in ('refine', 'exact'):
                    with self.subTest(bits=bits, unsafe=unsafe, mode=mode):
                        condition = 'answer==1' if unsafe else 'answer<0 || answer>1'
                        initial = '__VERIFIER_nondet_int()' if mode == 'refine' else '1'
                        source = prefix + 'int main(void) { int value=' + initial + '; int answer=choose(value); if(' + condition + ') reach_error(); }'
                        result = self.run_program(source, bits, mode)
                        self.assertEqual(result['safe'], not unsafe, result)
                        if mode == 'exact':
                            self.assertEqual(result['violation'], unsafe, result)
                        else:
                            self.assertNotIn('undefined value', result['gaps'])

    def test_source_scope_accepts_benign_compiler_warnings(self):
        source = '''extern void reach_error(void);
extern int __VERIFIER_nondet_int(void);
extern void metadata(const char *) __attribute__((__access__(__read_only__,1)));
int main(void) {
    unsigned short fixed=7;
    int value=__VERIFIER_nondet_int();
    if(fixed< -25 || value<0 || value>3) return 0;
    if(value>3) reach_error();
    return 0;
}
'''
        for bits in ('32', '64'):
            for unsafe in (False, True):
                with self.subTest(bits=bits, unsafe=unsafe):
                    result = self.run_program(source.replace('if(value>3)', 'if(value==2)') if unsafe else source,
                                              bits, 'refine')
                    self.assertEqual(result['safe'], not unsafe, result)
                    self.assertNotIn('unverified source scope', result['gaps'])

    def test_source_scope_still_rejects_semantic_warnings(self):
        from invariants import _source_loops

        programs = (
            'int main(void) { const int value=1; int *pointer=(int *)&value; return *pointer; }',
            'int main(void) { int value=0; return value++ + value++; }',
            'int main(void) { return missing_variable; }',
        )
        with tempfile.TemporaryDirectory(prefix='svf-scope-warnings-') as directory:
            source = Path(directory) / 'control.c'
            for bits in ('32', '64'):
                for program in programs:
                    with self.subTest(bits=bits, program=program):
                        source.write_text(program)
                        self.assertEqual(_source_loops(source, ('CallExpr', 'CompoundStmt', 'VarDecl'), bits), [])

    def test_refinement_modular_narrowing(self):
        from AbstractInterpretation import _ReachabilityRefinement
        for width in (1, 2, 4, 8):
            minimum, maximum = _ReachabilityRefinement.limits(width)
            for lower in range(-2 * (1 << width), 2 * (1 << width)):
                for span in (0, 1, (1 << width) - 1, 1 << width):
                    low, high = _ReachabilityRefinement.modular_bounds(lower, lower + span, width)
                    for number in range(lower, lower + span + 1):
                        converted = (number - minimum) % (1 << width) + minimum
                        self.assertTrue(minimum <= low <= converted <= high <= maximum)
        for bits in ('32', '64'):
            for relation, safe in (('!=', True), ('==', False)):
                source = ('extern long __VERIFIER_nondet_long(void); extern void reach_error(void); '
                          'int main(void) { long value=__VERIFIER_nondet_long(); '
                          'signed char saved=(signed char)value; if(saved' + relation
                          + '(signed char)value) reach_error(); }')
                with self.subTest(bits=bits, relation=relation):
                    self.assertEqual(self.run_program(source, bits, 'refinement')['safe'], safe)

    def test_scalar_loop_induction(self):
        prefix = 'extern void reach_error(void); extern int __VERIFIER_nondet_int(void);\n'
        bodies = (
            ('int value=0; int saved=0; while(1) { value=__VERIFIER_nondet_int(); '
             'if(value<0 || value>100) return 0; saved=value+3; '
             'if(saved!=value+3) reach_error(); }', True),
            ('int counter=0; while(1) { if(counter==1000) reach_error(); '
             'counter++; }', False),
            ('int value=0; int *pointer=&value; while(1) { '
             'if(pointer==0) reach_error(); pointer=0; }', False),
            ('int counter=0; while(counter<3) counter++; '
             'if(counter!=3) reach_error();', True),
        )
        for bits in ('32', '64'):
            for body, safe in bodies:
                with self.subTest(bits=bits, body=body):
                    result = self.run_program(prefix + 'int main(void) { ' + body + ' return 0; }', bits, 'refine')
                    self.assertEqual(result['safe'], safe, result)

    def test_refinement_repeated_expressions(self):
        prefix = 'extern void reach_error(void); extern int __VERIFIER_nondet_int(void);\n'
        bodies = (
            ('int value=__VERIFIER_nondet_int(); if(value<1 || value>100) return 0; '
             'signed char saved=(value/3)+2; if(saved!=(signed char)((value/3)+2)) reach_error();', True),
            ('int value=__VERIFIER_nondet_int(); if(value<1 || value>100) return 0; '
             'signed char saved=(value/3)+2; if(saved!=(signed char)((value/3)+3)) reach_error();', False),
            ('int value=__VERIFIER_nondet_int(); if(value<0 || value>100) return 0; '
             'int saved=value+3; if(saved!=value+3) reach_error();', True),
            ('int value=__VERIFIER_nondet_int(); if(value<0 || value>100) return 0; '
             'int saved=value+3; value=__VERIFIER_nondet_int(); '
             'if(value<0 || value>100) return 0; if(saved!=value+3) reach_error();', False),
            ('int value=__VERIFIER_nondet_int(); if(value<0 || value>100) return 0; '
             'int saved=value+3; int *alias=&value; *alias=value+1; '
             'if(saved!=value+3) reach_error();', False),
            ('int value=__VERIFIER_nondet_int(); if(value<0 || value>100) return 0; '
             'int saved; if(value>50) saved=value+3; else saved=value-3; '
             'if(value>50) { if(saved!=value+3) reach_error(); } '
             'else { if(saved!=value-3) reach_error(); }', True),
        )
        for bits in ('32', '64'):
            for body, safe in bodies:
                with self.subTest(bits=bits, body=body):
                    result = self.run_program(prefix + 'int main(void) { ' + body + ' return 0; }', bits, 'refine')
                    self.assertEqual(result['safe'], safe, result)

    def test_refinement_branching_helper_relationships(self):
        prefix = ('extern void reach_error(void); extern int __VERIFIER_nondet_int(void);\n'
                  'int choose(int first,int second) { if(first>second) return first; return second; }\n')
        for bits in ('32', '64'):
            for mutation in ('!=', '=='):
                source = prefix + ('int main(void) { int first=__VERIFIER_nondet_int(); '
                                   'int second=__VERIFIER_nondet_int(); int saved=choose(first,second); '
                                   'if(first>second) { if(saved' + mutation + 'first) reach_error(); } '
                                   'else { if(saved' + mutation + 'second) reach_error(); } return 0; }')
                with self.subTest(bits=bits, mutation=mutation):
                    result = self.run_program(source, bits, 'refine')
                    self.assertEqual(result['safe'], mutation == '!=', result)

    def test_refinement_symbolic_floating_expressions(self):
        prefix = 'extern void reach_error(void); extern double __VERIFIER_nondet_double(void);\n'
        bodies = (
            ('double value=__VERIFIER_nondet_double(); if(!(value>=1 && value<=100)) return 0; '
             'double saved=(value+3)*(value-2); if(saved!=(value+3)*(value-2)) reach_error();', True),
            ('double value=__VERIFIER_nondet_double(); if(value!=value) return 0; '
             'double saved=value; if(saved!=value) reach_error();', True),
            ('double value=__VERIFIER_nondet_double(); double saved=value; '
             'if(saved!=value) reach_error();', False),
            ('double value=__VERIFIER_nondet_double(); if(!(value>=0 && value<=100)) return 0; '
             'double saved=value+3; if(saved!=value+3) reach_error();', True),
            ('double value=__VERIFIER_nondet_double(); if(!(value>=0 && value<=100)) return 0; '
             'double saved=value+3; value=__VERIFIER_nondet_double(); '
             'if(!(value>=0 && value<=100)) return 0; if(saved!=value+3) reach_error();', False),
            ('double value=__VERIFIER_nondet_double(); if(value!=value) return 0; '
             'double saved=value/value; if(saved!=value/value) reach_error();', False),
            ('double value=__VERIFIER_nondet_double(); if(!(value>=1 && value<=100)) return 0; '
             'double saved=value/value; if(saved!=value/value) reach_error();', True),
            ('double value=__VERIFIER_nondet_double(); if(value!=value) return 0; '
             'double saved=value+3; double *alias=&value; *alias=7; '
             'if(saved!=value+3) reach_error();', False),
            ('double value=__VERIFIER_nondet_double(); '
             'if(!(value>=0 && value<=100)) return 0; '
             'double saved; if(value>50) saved=value+3; else saved=value-3; '
             'if(value>50) { if(saved!=value+3) reach_error(); } '
             'else { if(saved!=value-3) reach_error(); }', True),
        )
        for bits in ('32', '64'):
            for body, safe in bodies:
                with self.subTest(bits=bits, body=body):
                    result = self.run_program(prefix + 'int main(void) { ' + body + ' return 0; }', bits, 'refine')
                    self.assertEqual(result['safe'], safe, result)

    def test_floating_arithmetic_outward_enclosure(self):
        from AbstractInterpretation import _ReachabilityRefinement

        generator = random.Random(391)
        for width in (32, 64):
            for attempt in range(500):
                numbers = []
                while len(numbers) < 2:
                    packed = generator.getrandbits(width).to_bytes(width // 8, 'big')
                    number = struct.unpack('>f' if width == 32 else '>d', packed)[0]
                    if math.isfinite(number):
                        numbers.append(number)
                first, second = numbers
                for operation in (operator.add, operator.sub, operator.mul, operator.truediv):
                    if operation == operator.truediv and second == 0:
                        continue
                    exact = operation(Fraction.from_float(first), Fraction.from_float(second))
                    rounded = operation(first, second)
                    lower = _ReachabilityRefinement.floating_outward(rounded, width, False)
                    upper = _ReachabilityRefinement.floating_outward(rounded, width, True)
                    self.assertLessEqual(lower, exact, (width, first, second, operation))
                    self.assertGreaterEqual(upper, exact, (width, first, second, operation))

    def test_symbolic_floating_predicate_enclosure(self):
        from AbstractInterpretation import _PathFloat, _PathState, _ReachabilityRefinement

        refinement = _ReachabilityRefinement.__new__(_ReachabilityRefinement)
        accepted = (set(), {0}, {1}, {0, 1}, {-1}, {-1, 0}, {-1, 1}, {-1, 0, 1},
                    {2}, {0, 2}, {1, 2}, {0, 1, 2}, {-1, 2}, {-1, 0, 2}, {-1, 1, 2}, {-1, 0, 1, 2})
        numbers = (-math.inf, -100.0, -1.0, -0.0, 0.0, 1.0, 100.0, math.inf, math.nan)
        intervals = ((-math.inf, math.inf, True), (-math.inf, math.inf, False),
                     (-100.0, 100.0, False), (0.0, math.inf, True), (1.0, 0.0, True))
        for width in (32, 64):
            for low_left, high_left, nan_left in intervals:
                for low_right, high_right, nan_right in intervals:
                    left = _PathFloat(width, 1, low_left, high_left, nan_left)
                    right = _PathFloat(width, 2, low_right, high_right, nan_right)
                    for predicate in range(16):
                        lower, upper = refinement.floating_comparison(predicate, left, right)
                        for first in numbers:
                            if not (nan_left if math.isnan(first) else low_left <= first <= high_left):
                                continue
                            for second in numbers:
                                if not (nan_right if math.isnan(second) else low_right <= second <= high_right):
                                    continue
                                relation = 2 if math.isnan(first) or math.isnan(second) else (
                                    -1 if first < second else 1 if first > second else 0)
                                truth = relation in accepted[predicate]
                                self.assertTrue(lower <= int(truth) <= upper)
                                state = _PathState(None, values={1: left, 2: right})
                                self.assertTrue(refinement.floating_condition(state, predicate, left, right, truth))
                                for identifier, number in ((1, first), (2, second)):
                                    narrowed = state.values[identifier]
                                    self.assertTrue(narrowed.nan if math.isnan(number)
                                                    else narrowed.lower <= number <= narrowed.upper)
