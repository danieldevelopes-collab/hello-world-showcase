"""Registry of languages the wall tries to run.

Each Lang is fully data-driven. The runner resolves these placeholder tokens
inside `build` / `run` argument lists (never with a shell, always argv lists):

    {src}  -> absolute path to the written source file
    {exe}  -> absolute path to use for a compiled binary
    {dir}  -> the language's private working directory

Each entry also carries a short historical attribution (`creator`, `since`)
which is shown on the tile and expanded in the README. Longer credit
(committees, co-authors) lives in README.md.

`platforms` restricts a language to specific OSes (`darwin`, `linux`,
`windows`). Default `()` means all platforms.

Adding a language = adding one entry here. No other file needs to change.
"""

from dataclasses import dataclass, field
import platform
import sys
from typing import List, Tuple

from .portable import current_platform


@dataclass
class Lang:
    name: str                       # display name on the tile
    file: str                       # source file name written into {dir}
    source: str                     # the Hello World program text
    run: List[str]                  # argv to produce output (placeholders allowed)
    checks: List[str]               # executables that must all be on PATH
    build: List[List[str]] = field(default_factory=list)  # optional compile steps
    category: str = "easy"          # easy | compiled | ecosystem | tricky
    note: str = ""                  # short honesty note shown on the tile
    timeout: float = 0.0            # per-language override; 0 => runner default
    kind: str = "subprocess"        # "subprocess" or "browser" (runs in the page)
    creator: str = ""               # short attribution shown on the tile
    since: str = ""                 # year of first public release
    platforms: Tuple[str, ...] = () # () => all OSes; else subset of {darwin,linux,windows}


# --- Assembly: hand-written per OS+arch -------------------------------------
# macOS arm64: SVC #0x80, syscall in x16, entry _main (the C runtime calls
# main even though we never return to it).
_ASM_MACOS_ARM64 = """\
.global _main
.align 2
_main:
    mov     x0, #1                 // fd = stdout
    adrp    x1, msg@PAGE
    add     x1, x1, msg@PAGEOFF
    mov     x2, #12                // byte count
    mov     x16, #4                // write syscall
    svc     #0x80
    mov     x0, #0
    mov     x16, #1                // exit syscall
    svc     #0x80
.data
msg:
    .ascii  "Hello World\\n"
"""

# macOS x86_64: syscall numbers carry the 0x2000000 BSD class.
_ASM_MACOS_X86_64 = """\
.global _main
_main:
    movl    $0x2000004, %eax       # write
    movl    $1, %edi               # fd = stdout
    leaq    msg(%rip), %rsi
    movl    $12, %edx              # byte count
    syscall
    movl    $0x2000001, %eax       # exit
    xorl    %edi, %edi
    syscall
.data
msg:
    .ascii  "Hello World\\n"
"""

# Linux x86_64: write=1, exit=60, entry _start (we link with -nostdlib).
_ASM_LINUX_X86_64 = """\
.global _start
.text
_start:
    movq    $1, %rax               # sys_write
    movq    $1, %rdi               # fd = stdout
    leaq    msg(%rip), %rsi
    movq    $12, %rdx              # byte count
    syscall
    movq    $60, %rax              # sys_exit
    xorq    %rdi, %rdi
    syscall
.section .data
msg:
    .ascii  "Hello World\\n"
"""

# Linux aarch64: write=64, exit=93, entry _start, SVC #0.
_ASM_LINUX_ARM64 = """\
.global _start
.text
_start:
    mov     x0, #1                 // fd = stdout
    adr     x1, msg
    mov     x2, #12                // byte count
    mov     x8, #64                // sys_write
    svc     #0
    mov     x0, #0
    mov     x8, #93                // sys_exit
    svc     #0
.section .data
msg:
    .ascii  "Hello World\\n"
"""


def _assembly_lang() -> Lang:
    plat = current_platform()
    machine = platform.machine().lower()

    common = dict(
        name="Assembly", file="hello.s", category="tricky", timeout=20,
        creator="Kathleen Booth (first assembler)", since="1947",
    )

    if plat == "windows":
        # Genuinely hard to do portably (MSVC/MASM/link with kernel32).
        # We surface the limitation honestly instead of pretending.
        return Lang(
            run=["{exe}"], checks=["cc"],
            source="; Windows hello-world assembly requires MSVC/MASM + kernel32 linking\n",
            note="Windows asm needs MSVC/MASM; not attempted here",
            platforms=("darwin", "linux"), **common,
        )

    if plat == "darwin":
        if machine in ("arm64", "aarch64"):
            src, note = _ASM_MACOS_ARM64, "macOS arm64, raw write/exit syscalls"
        elif machine in ("x86_64", "amd64"):
            src, note = _ASM_MACOS_X86_64, "macOS x86_64, raw write/exit syscalls"
        else:
            src, note = "; unsupported architecture\n", f"no hand-written variant for {machine}"
        return Lang(
            source=src, build=[["cc", "{src}", "-o", "{exe}"]],
            run=["{exe}"], checks=["cc"], note=note, **common,
        )

    # linux
    if machine in ("arm64", "aarch64"):
        src, note = _ASM_LINUX_ARM64, "Linux arm64, raw write/exit syscalls"
    elif machine in ("x86_64", "amd64"):
        src, note = _ASM_LINUX_X86_64, "Linux x86_64, raw write/exit syscalls"
    else:
        src, note = "; unsupported architecture\n", f"no hand-written variant for {machine}"
    return Lang(
        source=src,
        build=[["cc", "{src}", "-o", "{exe}", "-nostdlib", "-static"]],
        run=["{exe}"], checks=["cc"], note=note, **common,
    )


def get_languages() -> List[Lang]:
    langs: List[Lang] = [
        # ---- almost always present: scripting + shells ----
        # Python: sys.executable is the interpreter running THIS controller,
        # which is guaranteed to exist on every platform we run on.
        Lang("Python", "hello.py", 'print("Hello World")\n',
             run=[sys.executable, "{src}"], checks=[],
             creator="Guido van Rossum", since="1991"),
        Lang("JavaScript", "hello.js", 'console.log("Hello World");\n',
             run=["node", "{src}"], checks=["node"], note="Node.js",
             creator="Brendan Eich", since="1995"),
        Lang("Ruby", "hello.rb", 'puts "Hello World"\n',
             run=["ruby", "{src}"], checks=["ruby"],
             creator='Yukihiro "Matz" Matsumoto', since="1995"),
        Lang("Perl", "hello.pl", 'print "Hello World\\n";\n',
             run=["perl", "{src}"], checks=["perl"],
             creator="Larry Wall", since="1987"),
        Lang("PHP", "hello.php", '<?php echo "Hello World\\n";\n',
             run=["php", "{src}"], checks=["php"],
             creator="Rasmus Lerdorf", since="1994"),
        Lang("Lua", "hello.lua", 'print("Hello World")\n',
             run=["lua", "{src}"], checks=["lua"],
             creator="Ierusalimschy, Figueiredo & Celes (PUC-Rio)", since="1993"),
        Lang("Bash", "hello.sh", 'echo "Hello World"\n',
             run=["bash", "{src}"], checks=["bash"],
             creator="Brian Fox (GNU)", since="1989"),
        Lang("Zsh", "hello.zsh", 'echo "Hello World"\n',
             run=["zsh", "{src}"], checks=["zsh"],
             creator="Paul Falstad", since="1990"),
        Lang("POSIX sh", "hello.posix.sh", 'echo "Hello World"\n',
             run=["sh", "{src}"], checks=["sh"],
             creator="Stephen Bourne (Bourne shell)", since="1977"),
        Lang("AWK", "hello.awk", 'BEGIN { print "Hello World" }\n',
             run=["awk", "-f", "{src}"], checks=["awk"],
             creator="Aho, Weinberger & Kernighan", since="1977"),
        Lang("Tcl", "hello.tcl", 'puts "Hello World"\n',
             run=["tclsh", "{src}"], checks=["tclsh"],
             creator="John Ousterhout", since="1988"),
        Lang("AppleScript", "hello.applescript", '"Hello World"\n',
             run=["osascript", "{src}"], checks=["osascript"],
             note="macOS osascript", platforms=("darwin",),
             creator="Apple (William Cook, architect)", since="1993"),
        Lang("SQL (SQLite)", "hello.sql", "-- run inline\n",
             run=["sqlite3", ":memory:", "select 'Hello World';"],
             checks=["sqlite3"], note="in-memory SELECT",
             creator="D. Richard Hipp · SQL by Chamberlin & Boyce, 1974",
             since="2000"),
        Lang("R", "hello.R", 'cat("Hello World\\n")\n',
             run=["Rscript", "{src}"], checks=["Rscript"], category="ecosystem",
             creator="Ross Ihaka & Robert Gentleman", since="1993"),
        Lang("PowerShell", "hello.ps1", 'Write-Output "Hello World"\n',
             run=["pwsh", "-NoProfile", "-File", "{src}"], checks=["pwsh"],
             category="ecosystem",
             creator="Jeffrey Snover (Microsoft)", since="2006"),

        # ---- Windows-only ----
        Lang("Windows PowerShell", "hello.ps1", 'Write-Output "Hello World"\n',
             run=["powershell", "-NoProfile", "-File", "{src}"],
             checks=["powershell"], category="ecosystem",
             platforms=("windows",), note="bundled with Windows",
             creator="Jeffrey Snover (Microsoft)", since="2006"),
        Lang("Batch (cmd)", "hello.bat", "@echo Hello World\r\n",
             run=["cmd", "/c", "{src}"], checks=["cmd"], category="easy",
             platforms=("windows",), note="DOS-lineage command shell",
             creator="Microsoft (DOS lineage, Tim Paterson)", since="1980"),

        # ---- compiled with the C/C++/Obj-C/Swift toolchain ----
        Lang("C", "hello.c",
             '#include <stdio.h>\nint main(void){ printf("Hello World\\n"); return 0; }\n',
             build=[["cc", "{src}", "-o", "{exe}"]], run=["{exe}"],
             checks=["cc"], category="compiled",
             creator="Dennis Ritchie (Bell Labs)", since="1972"),
        Lang("C++", "hello.cpp",
             '#include <iostream>\nint main(){ std::cout << "Hello World" << std::endl; return 0; }\n',
             build=[["c++", "{src}", "-o", "{exe}"]], run=["{exe}"],
             checks=["c++"], category="compiled",
             creator="Bjarne Stroustrup (Bell Labs)", since="1985"),
        Lang("Objective-C", "hello.m",
             '#import <Foundation/Foundation.h>\n'
             'int main(){ @autoreleasepool { printf("Hello World\\n"); } return 0; }\n',
             build=[["clang", "{src}", "-framework", "Foundation", "-o", "{exe}"]],
             run=["{exe}"], checks=["clang"], category="compiled",
             platforms=("darwin",),
             note="needs Foundation (macOS frameworks)",
             creator="Brad Cox & Tom Love", since="1984"),
        Lang("Swift", "hello.swift", 'print("Hello World")\n',
             run=["swift", "{src}"], checks=["swift"], category="compiled",
             note="script mode", timeout=60,
             creator="Chris Lattner (Apple)", since="2014"),
        _assembly_lang(),

        # ---- JVM family ----
        Lang("Java", "Hello.java",
             'public class Hello {\n'
             '  public static void main(String[] a){ System.out.println("Hello World"); }\n'
             '}\n',
             build=[["javac", "{src}"]], run=["java", "-cp", "{dir}", "Hello"],
             checks=["javac", "java"], category="ecosystem", timeout=60,
             creator="James Gosling (Sun)", since="1995"),
        Lang("Kotlin", "Hello.kt", 'fun main(){ println("Hello World") }\n',
             build=[["kotlinc", "{src}", "-include-runtime", "-d", "{dir}/hello.jar"]],
             run=["java", "-jar", "{dir}/hello.jar"],
             checks=["kotlinc", "java"], category="ecosystem",
             note="slow: JVM compile", timeout=150,
             creator="Andrey Breslav (JetBrains)", since="2011"),
        Lang("Scala", "Hello.scala",
             'object Hello extends App { println("Hello World") }\n',
             run=["scala", "{src}"], checks=["scala"], category="ecosystem",
             timeout=120,
             creator="Martin Odersky (EPFL)", since="2004"),
        Lang("Groovy", "hello.groovy", 'println "Hello World"\n',
             run=["groovy", "{src}"], checks=["groovy"], category="ecosystem",
             timeout=60,
             creator="James Strachan", since="2003"),

        # ---- other ecosystems (run if installed, else honest fallback) ----
        Lang("Go", "hello.go",
             'package main\nimport "fmt"\nfunc main(){ fmt.Println("Hello World") }\n',
             run=["go", "run", "{src}"], checks=["go"], category="ecosystem",
             timeout=60,
             creator="Griesemer, Pike & Thompson (Google)", since="2009"),
        Lang("Rust", "hello.rs", 'fn main(){ println!("Hello World"); }\n',
             build=[["rustc", "{src}", "-o", "{exe}"]], run=["{exe}"],
             checks=["rustc"], category="ecosystem", timeout=60,
             creator="Graydon Hoare (Mozilla)", since="2010"),
        Lang("TypeScript", "hello.ts",
             'const m: string = "Hello World";\nconsole.log(m);\n',
             run=["ts-node", "{src}"], checks=["ts-node"], category="ecosystem",
             note="via ts-node",
             creator="Anders Hejlsberg (Microsoft)", since="2012"),
        Lang("TypeScript (Deno)", "hello.deno.ts", 'console.log("Hello World");\n',
             run=["deno", "run", "{src}"], checks=["deno"], category="ecosystem",
             creator="Ryan Dahl (Deno) · TS by Hejlsberg, 2012", since="2018"),
        Lang("Dart", "hello.dart", 'void main(){ print("Hello World"); }\n',
             run=["dart", "{src}"], checks=["dart"], category="ecosystem",
             timeout=60,
             creator="Lars Bak & Kasper Lund (Google)", since="2011"),
        Lang("C# (Mono)", "Hello.cs",
             'class Hello { static void Main(){ System.Console.WriteLine("Hello World"); } }\n',
             build=[["mcs", "{src}", "-out:{dir}/hello.exe"]],
             run=["mono", "{dir}/hello.exe"],
             checks=["mcs", "mono"], category="ecosystem",
             creator="Miguel de Icaza (Mono) · C# by Hejlsberg, 2000",
             since="2004"),
        Lang("Haskell", "hello.hs", 'main = putStrLn "Hello World"\n',
             run=["runghc", "{src}"], checks=["runghc"], category="ecosystem",
             timeout=60,
             creator="Haskell Committee", since="1990"),
        Lang("Julia", "hello.jl", 'println("Hello World")\n',
             run=["julia", "{src}"], checks=["julia"], category="ecosystem",
             timeout=60,
             creator="Bezanson, Karpinski, Shah & Edelman (MIT)", since="2012"),
        Lang("Elixir", "hello.exs", 'IO.puts "Hello World"\n',
             run=["elixir", "{src}"], checks=["elixir"], category="ecosystem",
             timeout=60,
             creator="José Valim", since="2011"),
        Lang("Erlang", "hello.erl",
             '#!/usr/bin/env escript\nmain(_) -> io:format("Hello World~n").\n',
             run=["escript", "{src}"], checks=["escript"], category="ecosystem",
             creator="Armstrong, Virding & Williams (Ericsson)", since="1986"),
        Lang("Crystal", "hello.cr", 'puts "Hello World"\n',
             run=["crystal", "run", "--no-color", "{src}"], checks=["crystal"],
             category="ecosystem", timeout=90,
             creator="Ary Borenszweig & Juan Wajnerman", since="2014"),
        Lang("Nim", "hello.nim", 'echo "Hello World"\n',
             build=[["nim", "c", "--hints:off", "-o:{exe}", "{src}"]], run=["{exe}"],
             checks=["nim"], category="ecosystem", timeout=90,
             creator="Andreas Rumpf", since="2008"),
        Lang("Zig", "hello.zig",
             'const std = @import("std");\n'
             'pub fn main() !void {\n'
             '    try std.io.getStdOut().writeAll("Hello World\\n");\n'
             '}\n',
             run=["zig", "run", "{src}"], checks=["zig"], category="ecosystem",
             timeout=90,
             creator="Andrew Kelley", since="2016"),
        Lang("Fortran", "hello.f90",
             'program hello\n  print *, "Hello World"\nend program hello\n',
             build=[["gfortran", "{src}", "-o", "{exe}"]], run=["{exe}"],
             checks=["gfortran"], category="ecosystem", timeout=60,
             creator="John Backus (IBM)", since="1957"),

        # ---- runs inside the very browser that shows the wall ----
        Lang("HTML / JavaScript", "hello.html", "",
             run=[], checks=[], category="easy", kind="browser",
             note="executed live in this page",
             creator="Tim Berners-Lee (HTML) · JS by Eich, 1995", since="1991"),
    ]
    return langs
