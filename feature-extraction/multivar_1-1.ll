; ModuleID = './multivar_1-1.ll'
source_filename = "multivar_1-1.c"
target datalayout = "e-m:o-i64:64-i128:128-n32:64-S128"
target triple = "arm64-apple-macosx14.0.0"

@.str = private unnamed_addr constant [2 x i8] c"0\00", align 1, !dbg !0
@.str.1 = private unnamed_addr constant [15 x i8] c"multivar_1-1.c\00", align 1, !dbg !7
@.str.2 = private unnamed_addr constant [12 x i8] c"reach_error\00", align 1, !dbg !12

; Function Attrs: noinline nounwind ssp uwtable(sync)
define void @reach_error() #0 !dbg !26 {
entry:
  call void @__assert_fail(ptr noundef @.str, ptr noundef @.str.1, i32 noundef 3, ptr noundef @.str.2) #5, !dbg !30
  unreachable, !dbg !30
}

; Function Attrs: nocallback noreturn nounwind
declare void @__assert_fail(ptr noundef, ptr noundef, i32 noundef, ptr noundef) #1

; Function Attrs: noinline nounwind ssp uwtable(sync)
define void @__VERIFIER_assert(i32 noundef %cond) #0 !dbg !31 {
entry:
  call void @llvm.dbg.value(metadata i32 %cond, metadata !35, metadata !DIExpression()), !dbg !36
  %tobool = icmp ne i32 %cond, 0, !dbg !37
  br i1 %tobool, label %if.end, label %if.then, !dbg !39

if.then:                                          ; preds = %entry
  br label %ERROR, !dbg !40

ERROR:                                            ; preds = %if.then
  call void @llvm.dbg.label(metadata !41), !dbg !43
  call void @reach_error(), !dbg !44
  call void @abort() #6, !dbg !46
  unreachable, !dbg !46

if.end:                                           ; preds = %entry
  ret void, !dbg !47
}

; Function Attrs: nocallback nofree nosync nounwind speculatable willreturn memory(none)
declare void @llvm.dbg.declare(metadata, metadata, metadata) #2

; Function Attrs: nocallback nofree nosync nounwind speculatable willreturn memory(none)
declare void @llvm.dbg.label(metadata) #2

; Function Attrs: noreturn
declare void @abort() #3

; Function Attrs: noinline nounwind ssp uwtable(sync)
define i32 @main() #0 !dbg !48 {
entry:
  %call = call i32 @__VERIFIER_nondet_uint(), !dbg !51
  call void @llvm.dbg.value(metadata i32 %call, metadata !52, metadata !DIExpression()), !dbg !54
  call void @llvm.dbg.value(metadata i32 %call, metadata !55, metadata !DIExpression()), !dbg !54
  br label %while.cond, !dbg !56

while.cond:                                       ; preds = %while.body, %entry
  %x.0 = phi i32 [ %call, %entry ], [ %inc, %while.body ], !dbg !54
  %y.0 = phi i32 [ %call, %entry ], [ %inc1, %while.body ], !dbg !54
  call void @llvm.dbg.value(metadata i32 %y.0, metadata !55, metadata !DIExpression()), !dbg !54
  call void @llvm.dbg.value(metadata i32 %x.0, metadata !52, metadata !DIExpression()), !dbg !54
  %cmp = icmp ult i32 %x.0, 1024, !dbg !57
  br i1 %cmp, label %while.body, label %while.end, !dbg !56

while.body:                                       ; preds = %while.cond
  %inc = add i32 %x.0, 1, !dbg !58
  call void @llvm.dbg.value(metadata i32 %inc, metadata !52, metadata !DIExpression()), !dbg !54
  %inc1 = add i32 %y.0, 1, !dbg !60
  call void @llvm.dbg.value(metadata i32 %inc1, metadata !55, metadata !DIExpression()), !dbg !54
  br label %while.cond, !dbg !56, !llvm.loop !61

while.end:                                        ; preds = %while.cond
  %cmp2 = icmp eq i32 %x.0, %y.0, !dbg !64
  %conv = zext i1 %cmp2 to i32, !dbg !64
  call void @__VERIFIER_assert(i32 noundef %conv), !dbg !65
  ret i32 0, !dbg !66
}

declare i32 @__VERIFIER_nondet_uint() #4

; Function Attrs: nocallback nofree nosync nounwind speculatable willreturn memory(none)
declare void @llvm.dbg.value(metadata, metadata, metadata) #2

attributes #0 = { noinline nounwind ssp uwtable(sync) "frame-pointer"="non-leaf" "no-trapping-math"="true" "stack-protector-buffer-size"="8" "target-cpu"="apple-m1" "target-features"="+aes,+crc,+crypto,+dotprod,+fp-armv8,+fp16fml,+fullfp16,+lse,+neon,+ras,+rcpc,+rdm,+sha2,+sha3,+sm4,+v8.1a,+v8.2a,+v8.3a,+v8.4a,+v8.5a,+v8a,+zcm,+zcz" }
attributes #1 = { nocallback noreturn nounwind "frame-pointer"="non-leaf" "no-trapping-math"="true" "stack-protector-buffer-size"="8" "target-cpu"="apple-m1" "target-features"="+aes,+crc,+crypto,+dotprod,+fp-armv8,+fp16fml,+fullfp16,+lse,+neon,+ras,+rcpc,+rdm,+sha2,+sha3,+sm4,+v8.1a,+v8.2a,+v8.3a,+v8.4a,+v8.5a,+v8a,+zcm,+zcz" }
attributes #2 = { nocallback nofree nosync nounwind speculatable willreturn memory(none) }
attributes #3 = { noreturn "frame-pointer"="non-leaf" "no-trapping-math"="true" "stack-protector-buffer-size"="8" "target-cpu"="apple-m1" "target-features"="+aes,+crc,+crypto,+dotprod,+fp-armv8,+fp16fml,+fullfp16,+lse,+neon,+ras,+rcpc,+rdm,+sha2,+sha3,+sm4,+v8.1a,+v8.2a,+v8.3a,+v8.4a,+v8.5a,+v8a,+zcm,+zcz" }
attributes #4 = { "frame-pointer"="non-leaf" "no-trapping-math"="true" "stack-protector-buffer-size"="8" "target-cpu"="apple-m1" "target-features"="+aes,+crc,+crypto,+dotprod,+fp-armv8,+fp16fml,+fullfp16,+lse,+neon,+ras,+rcpc,+rdm,+sha2,+sha3,+sm4,+v8.1a,+v8.2a,+v8.3a,+v8.4a,+v8.5a,+v8a,+zcm,+zcz" }
attributes #5 = { nocallback noreturn nounwind }
attributes #6 = { noreturn }

!llvm.dbg.cu = !{!17}
!llvm.module.flags = !{!19, !20, !21, !22, !23, !24}
!llvm.ident = !{!25}

!0 = !DIGlobalVariableExpression(var: !1, expr: !DIExpression())
!1 = distinct !DIGlobalVariable(scope: null, file: !2, line: 3, type: !3, isLocal: true, isDefinition: true)
!2 = !DIFile(filename: "multivar_1-1.c", directory: "/Users/z5489735/2023/0424/Software-Security-Analysis/SVC-Extraction")
!3 = !DICompositeType(tag: DW_TAG_array_type, baseType: !4, size: 16, elements: !5)
!4 = !DIBasicType(name: "char", size: 8, encoding: DW_ATE_signed_char)
!5 = !{!6}
!6 = !DISubrange(count: 2)
!7 = !DIGlobalVariableExpression(var: !8, expr: !DIExpression())
!8 = distinct !DIGlobalVariable(scope: null, file: !2, line: 3, type: !9, isLocal: true, isDefinition: true)
!9 = !DICompositeType(tag: DW_TAG_array_type, baseType: !4, size: 120, elements: !10)
!10 = !{!11}
!11 = !DISubrange(count: 15)
!12 = !DIGlobalVariableExpression(var: !13, expr: !DIExpression())
!13 = distinct !DIGlobalVariable(scope: null, file: !2, line: 3, type: !14, isLocal: true, isDefinition: true)
!14 = !DICompositeType(tag: DW_TAG_array_type, baseType: !4, size: 96, elements: !15)
!15 = !{!16}
!16 = !DISubrange(count: 12)
!17 = distinct !DICompileUnit(language: DW_LANG_C11, file: !2, producer: "Homebrew clang version 16.0.6", isOptimized: false, runtimeVersion: 0, emissionKind: FullDebug, globals: !18, splitDebugInlining: false, nameTableKind: None, sysroot: "/Library/Developer/CommandLineTools/SDKs/MacOSX14.sdk", sdk: "MacOSX14.sdk")
!18 = !{!0, !7, !12}
!19 = !{i32 7, !"Dwarf Version", i32 4}
!20 = !{i32 2, !"Debug Info Version", i32 3}
!21 = !{i32 1, !"wchar_size", i32 4}
!22 = !{i32 8, !"PIC Level", i32 2}
!23 = !{i32 7, !"uwtable", i32 1}
!24 = !{i32 7, !"frame-pointer", i32 1}
!25 = !{!"Homebrew clang version 16.0.6"}
!26 = distinct !DISubprogram(name: "reach_error", scope: !2, file: !2, line: 3, type: !27, scopeLine: 3, spFlags: DISPFlagDefinition, unit: !17, retainedNodes: !29)
!27 = !DISubroutineType(types: !28)
!28 = !{null}
!29 = !{}
!30 = !DILocation(line: 3, column: 22, scope: !26)
!31 = distinct !DISubprogram(name: "__VERIFIER_assert", scope: !2, file: !2, line: 6, type: !32, scopeLine: 6, flags: DIFlagPrototyped, spFlags: DISPFlagDefinition, unit: !17, retainedNodes: !29)
!32 = !DISubroutineType(types: !33)
!33 = !{null, !34}
!34 = !DIBasicType(name: "int", size: 32, encoding: DW_ATE_signed)
!35 = !DILocalVariable(name: "cond", arg: 1, scope: !31, file: !2, line: 6, type: !34)
!36 = !DILocation(line: 0, scope: !31)
!37 = !DILocation(line: 7, column: 8, scope: !38)
!38 = distinct !DILexicalBlock(scope: !31, file: !2, line: 7, column: 7)
!39 = !DILocation(line: 7, column: 7, scope: !31)
!40 = !DILocation(line: 7, column: 16, scope: !38)
!41 = !DILabel(scope: !42, name: "ERROR", file: !2, line: 8)
!42 = distinct !DILexicalBlock(scope: !38, file: !2, line: 7, column: 16)
!43 = !DILocation(line: 8, column: 5, scope: !42)
!44 = !DILocation(line: 8, column: 13, scope: !45)
!45 = distinct !DILexicalBlock(scope: !42, file: !2, line: 8, column: 12)
!46 = !DILocation(line: 8, column: 27, scope: !45)
!47 = !DILocation(line: 10, column: 3, scope: !31)
!48 = distinct !DISubprogram(name: "main", scope: !2, file: !2, line: 13, type: !49, scopeLine: 13, flags: DIFlagPrototyped, spFlags: DISPFlagDefinition, unit: !17, retainedNodes: !29)
!49 = !DISubroutineType(types: !50)
!50 = !{!34}
!51 = !DILocation(line: 14, column: 20, scope: !48)
!52 = !DILocalVariable(name: "x", scope: !48, file: !2, line: 14, type: !53)
!53 = !DIBasicType(name: "unsigned int", size: 32, encoding: DW_ATE_unsigned)
!54 = !DILocation(line: 0, scope: !48)
!55 = !DILocalVariable(name: "y", scope: !48, file: !2, line: 15, type: !53)
!56 = !DILocation(line: 17, column: 3, scope: !48)
!57 = !DILocation(line: 17, column: 12, scope: !48)
!58 = !DILocation(line: 18, column: 6, scope: !59)
!59 = distinct !DILexicalBlock(scope: !48, file: !2, line: 17, column: 20)
!60 = !DILocation(line: 19, column: 6, scope: !59)
!61 = distinct !{!61, !56, !62, !63}
!62 = !DILocation(line: 20, column: 3, scope: !48)
!63 = !{!"llvm.loop.mustprogress"}
!64 = !DILocation(line: 22, column: 23, scope: !48)
!65 = !DILocation(line: 22, column: 3, scope: !48)
!66 = !DILocation(line: 23, column: 1, scope: !48)
