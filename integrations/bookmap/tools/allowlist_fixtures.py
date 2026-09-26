"""BMREC-04(a): mutation tests of the allowlist check itself.

Each must-fail fixture is ONE small class added to the real, clean add-on classes. The resulting jar must FAIL the
check with the expected rule AND a message naming the forbidden item -- so a fixture cannot "pass the test" by
failing for an unrelated reason. The clean case is the real add-on jar, which must PASS.

    import allowlist_fixtures as AF
    results = AF.run(javac, classes_dir, compile_cp, work_dir, allowlist)   # list of dicts

Standard library only. Used by integrations/bookmap/build.py (every build) and by
scripts/tests/test_h1_bookmap_recorder.py.
"""
import os
import shutil
import subprocess
import zipfile

import allowlist_check as AC

PKG = "tds.bookmap.recorder"
IMPORTS = """
import velox.api.layer1.*;
import velox.api.layer1.data.*;
import velox.api.layer1.simplified.*;
import velox.api.layer1.annotations.*;
"""

# (name, expected_rule, expected_message_substring, class_body_or_full_source)
# A body starting with "@" or "abstract"/"class" is a full class declaration; otherwise it is wrapped in
# `final class Fx_<name> { ... }`.
FIXTURES = [
    # --- BMREC-01: trading capability and account data, on ANY owner type
    ("api_sendOrder", "BMREC-01", "Api.sendOrder", "void f(Api a) { a.sendOrder(null); }"),
    ("api_updateOrder", "BMREC-01", "Api.updateOrder", "void f(Api a) { a.updateOrder(null); }"),
    ("provider_sendOrder", "BMREC-01", "Layer1ApiProvider.sendOrder",
     "void f(Api a) { Layer1ApiProvider p = a.getProvider(); p.sendOrder(null); }"),
    ("trading_provider_sendOrder", "BMREC-01", "Layer1ApiTradingProvider",
     "static void f(Layer1ApiTradingProvider p) { p.sendOrder(null); }"),
    ("provider_updateOrder", "BMREC-01", "Layer1ApiProvider.updateOrder",
     "void f(Api a) { Layer1ApiProvider p = a.getProvider(); p.updateOrder(null); }"),
    ("provider_login", "BMREC-01", "Layer1ApiProvider.login",
     "void f(Api a) { Layer1ApiProvider p = a.getProvider(); p.login(null); }"),
    ("provider_sendUserMessage", "BMREC-01", "Layer1ApiProvider.sendUserMessage",
     "void f(Api a) { Layer1ApiProvider p = a.getProvider(); p.sendUserMessage(null); }"),
    ("provider_close", "BMREC-01", "Layer1ApiProvider.close",
     "void f(Api a) { Layer1ApiProvider p = a.getProvider(); p.close(); }"),
    ("admin_provider_login", "BMREC-01", "Layer1ApiAdminProvider",
     "static void f(Layer1ApiAdminProvider p) { p.login(null); }"),
    ("api_sendUserMessage", "BMREC-01", "Api.sendUserMessage", "void f(Api a) { a.sendUserMessage(null); }"),
    ("trading_listener", "BMREC-01", "Layer1ApiTradingListener",
     "abstract class Fx_trading_listener implements Layer1ApiTradingListener { }"),
    ("trading_listenable", "BMREC-01", "Layer1ApiTradingListenable",
     "static void f(Layer1ApiTradingListenable l) { l.addListener((Layer1ApiTradingListener) null); }"),
    ("orders_listener", "BMREC-01", "OrdersListener",
     "abstract class Fx_orders_listener implements OrdersListener { }"),
    ("position_listener", "BMREC-01", "PositionListener",
     "abstract class Fx_position_listener implements PositionListener { }"),
    ("balance_listener", "BMREC-01", "BalanceListener",
     "abstract class Fx_balance_listener implements BalanceListener { }"),
    ("orders_adapter", "BMREC-01", "OrdersAdapter", "class Fx_orders_adapter implements OrdersAdapter { }"),
    ("position_adapter", "BMREC-01", "PositionAdapter", "class Fx_position_adapter implements PositionAdapter { }"),
    ("balance_adapter", "BMREC-01", "BalanceAdapter", "class Fx_balance_adapter implements BalanceAdapter { }"),
    ("api_addOrdersListeners", "BMREC-01", "Api.addOrdersListeners",
     "void f(Api a) { a.addOrdersListeners(null); }"),
    ("trading_strategy_annotation", "BMREC-01", "Layer1TradingStrategy",
     "@Layer1TradingStrategy final class Fx_trading_strategy_annotation { }"),
    ("unrestricted_data_annotation", "BMREC-01", "UnrestrictedData",
     "@UnrestrictedData final class Fx_unrestricted_data_annotation { }"),
    ("register_indicator", "BMREC-01", "Api.registerIndicator",
     "void f(Api a) { a.registerIndicator(\"x\", null); }"),
    ("register_indicator_modifiable", "BMREC-01", "Api.registerIndicatorModifiable",
     "void f(Api a) { a.registerIndicatorModifiable(\"x\", null); }"),

    # --- BMREC-02: getProvider is one site, result only receives add/removeListener(admin)
    ("getprovider_stored_in_field", "BMREC-02", "field of provider type",
     "Layer1ApiProvider held; void f(Api a) { held = a.getProvider(); }"),
    ("getprovider_passed_to_method", "BMREC-02", "must go straight into a local",
     "void f(Api a) { g(a.getProvider()); } static void g(Object o) { }"),
    ("getprovider_trading_overload", "BMREC-02", "used other than as the receiver",
     "void f(Api a, Layer1ApiTradingListener l) { Layer1ApiProvider p = a.getProvider(); p.addListener(l); }"),
    ("getprovider_second_site", "BMREC-02", "exactly one site; found 2",
     "void f(Api a, ConnectionListener l) { Layer1ApiProvider p = a.getProvider(); p.addListener(l); }"),
    ("getprovider_returned", "BMREC-02", "method descriptor carries provider type",
     "Layer1ApiProvider f(Api a) { Layer1ApiProvider p = a.getProvider(); return p; }"),
    ("provider_cast", "BMREC-02", "checkcast to velox type",
     "void f(Object o) { Layer1ApiProvider p = (Layer1ApiProvider) o; }"),
    ("getprovider_other_method", "BMREC-02", "used other than as the receiver",
     "long f(Api a) { Layer1ApiProvider p = a.getProvider(); return p.getCurrentTime(); }"),
    ("getprovider_wrong_class", "BMREC-02", "exactly one site; found 2",
     "void f(Api a) { Layer1ApiProvider p = a.getProvider(); }"),

    # --- BMREC-03: no dynamic reach, no I/O except the one pipe open
    ("reflection_method", "BMREC-03", "java/lang/reflect/Method",
     "Object f() throws Exception { return String.class.getMethod(\"length\"); }"),
    ("method_handles_lookup", "BMREC-03", "MethodHandles$Lookup.findVirtual",
     "Object f() throws Exception { return java.lang.invoke.MethodHandles.lookup().findVirtual("
     "String.class, \"length\", java.lang.invoke.MethodType.methodType(int.class)); }"),
    ("class_forName", "BMREC-03", "java/lang/Class.forName",
     "Object f() throws Exception { return Class.forName(\"x.Y\"); }"),
    ("classloader_subclass", "BMREC-03", "java/lang/ClassLoader",
     "class Fx_classloader_subclass extends ClassLoader { }"),
    ("url_classloader", "BMREC-03", "java/net/URLClassLoader",
     "Object f() { return new java.net.URLClassLoader(new java.net.URL[0]); }"),
    ("service_loader", "BMREC-03", "java/util/ServiceLoader",
     "Object f() { return java.util.ServiceLoader.load(Runnable.class); }"),
    ("sun_misc_unsafe", "BMREC-03", "sun/misc/Unsafe", "static void f(sun.misc.Unsafe u) { }"),
    ("thread_context_classloader", "BMREC-03", "java/lang/Thread.getContextClassLoader",
     "Object f() { return Thread.currentThread().getContextClassLoader(); }"),
    ("system_loadLibrary", "BMREC-03", "java/lang/System.loadLibrary",
     "void f() { System.loadLibrary(\"x\"); }"),
    ("system_load", "BMREC-03", "java/lang/System.load", "void f() { System.load(\"x\"); }"),
    ("native_method", "BMREC-03", "native method", "native void f();"),
    ("runtime_exec", "BMREC-03", "java/lang/Runtime",
     "Object f() throws Exception { return Runtime.getRuntime().exec(new String[] {\"x\"}); }"),
    ("process_builder", "BMREC-03", "java/lang/ProcessBuilder",
     "Object f() throws Exception { return new ProcessBuilder(\"x\").start(); }"),
    ("system_exit", "BMREC-03", "java/lang/System.exit", "void f() { System.exit(0); }"),
    ("net_socket", "BMREC-03", "java/net/Socket", "Object f() { return new java.net.Socket(); }"),
    ("net_url", "BMREC-03", "java/net/URL",
     "Object f() throws Exception { return java.net.URI.create(\"http://x\").toURL().openStream(); }"),
    ("net_http_client", "BMREC-03", "java/net/http/HttpClient",
     "Object f() { return java.net.http.HttpClient.newHttpClient(); }"),
    ("socket_channel", "BMREC-03", "java/nio/channels/SocketChannel",
     "Object f() throws Exception { return java.nio.channels.SocketChannel.open(); }"),
    ("object_output_stream", "BMREC-03", "java/io/ObjectOutputStream",
     "Object f() throws Exception { return new java.io.ObjectOutputStream(null); }"),
    ("object_input_stream", "BMREC-03", "java/io/ObjectInputStream",
     "Object f() throws Exception { return new java.io.ObjectInputStream(null); }"),
    ("files_write", "BMREC-03", "java/nio/file/Files",
     "void f() throws Exception { java.nio.file.Files.write(java.nio.file.Path.of(\"x\"), new byte[0]); }"),
    ("file_writer", "BMREC-03", "java/io/FileWriter",
     "Object f() throws Exception { return new java.io.FileWriter(\"x\"); }"),
    ("fos_non_pipe_path", "BMREC-03", "does not start with",
     "Object f() throws Exception { return new java.io.FileOutputStream(\"C:\\\\x.txt\", true); }"),
    ("fos_second_pipe_site", "BMREC-03", "exactly one FileOutputStream construction is allowed; found 2",
     "Object f() throws Exception { return new java.io.FileOutputStream(\"\\\\\\\\.\\\\pipe\\\\other\", true); }"),
    ("fos_dynamic_path", "BMREC-03", "not an ldc string constant",
     "Object f(String s) throws Exception { return new java.io.FileOutputStream(s, true); }"),
    ("fos_one_arg_ctor", "BMREC-03", "must be constructed as (String path, true)",
     "Object f() throws Exception { return new java.io.FileOutputStream(\"\\\\\\\\.\\\\pipe\\\\x\"); }"),
    ("indy_switch_bootstrap", "BMREC-03", "SwitchBootstraps.typeSwitch is not allowed",
     "int f(Object o) { return switch (o) { case String s -> 1; default -> 0; }; }"),

    # --- BMREC-05: nothing may read from the pipe
    ("pipe_read_file_input_stream", "BMREC-03", "java/io/FileInputStream",
     "Object f() throws Exception { return new java.io.FileInputStream(\"\\\\\\\\.\\\\pipe\\\\x\"); }"),
    ("pipe_read_random_access_file", "BMREC-03", "java/io/RandomAccessFile",
     "Object f() throws Exception { return new java.io.RandomAccessFile(\"\\\\\\\\.\\\\pipe\\\\x\", \"rw\"); }"),
    ("pipe_get_channel", "BMREC-03", "java/io/FileOutputStream.getChannel",
     "Object f(java.io.FileOutputStream o) { return o.getChannel(); }"),

    # --- BMREC-31: only project classes in the jar
    ("jar_foreign_package", "BMREC-31", "outside the project package", "@PKG=tdsfixture.other"),
]


def _source(name, body):
    if body.startswith("@PKG="):
        pkg = body[len("@PKG="):]
        return pkg, f"package {pkg};\nfinal class Fx_{name} {{ }}\n"
    if body.startswith("@") or body.startswith("abstract ") or body.startswith("class "):
        decl = body
    else:
        decl = f"final class Fx_{name} {{\n    {body}\n}}"
    return PKG, f"package {PKG};\n{IMPORTS}\n{decl}\n"


def run(javac, classes_dir, compile_cp, work_dir, allowlist, clean_jar):
    """Compile every fixture (one javac run), build one jar per fixture = clean classes + that fixture's classes,
    run the check. Returns a list of result dicts; the clean jar's result is first."""
    src_root = os.path.join(work_dir, "fixture-src")
    out_root = os.path.join(work_dir, "fixture-classes")
    for d in (src_root, out_root):
        shutil.rmtree(d, ignore_errors=True)
        os.makedirs(d)
    files = []
    for name, _rule, _sub, body in FIXTURES:
        pkg, src = _source(name, body)
        d = os.path.join(src_root, *pkg.split("."))
        os.makedirs(d, exist_ok=True)
        p = os.path.join(d, f"Fx_{name}.java")
        with open(p, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(src)
        files.append(p)
    cp = os.pathsep.join(list(compile_cp) + [classes_dir])
    proc = subprocess.run([javac, "-nowarn", "-XDsuppressNotes", "-cp", cp, "-d", out_root] + files,
                          capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError("fixture compilation failed:\n" + proc.stdout + proc.stderr)
    results = []
    v, _f = AC.check_jar(clean_jar, allowlist)
    results.append({"name": "CLEAN(real add-on jar)", "expect": "PASS", "ok": not v,
                    "violations": v})
    for name, rule, sub, body in FIXTURES:
        pkg, _src = _source(name, body)
        jar = os.path.join(work_dir, f"fixture-{name}.jar")
        with zipfile.ZipFile(clean_jar) as src, zipfile.ZipFile(jar, "w") as dst:
            for info in src.infolist():
                dst.writestr(info, src.read(info.filename))
            pdir = os.path.join(out_root, *pkg.split("."))
            for fn in sorted(os.listdir(pdir)):
                if fn == f"Fx_{name}.class" or fn.startswith(f"Fx_{name}$"):
                    dst.write(os.path.join(pdir, fn), pkg.replace(".", "/") + "/" + fn)
        v, _f = AC.check_jar(jar, allowlist)
        hit = any(r == rule and sub in m for r, m in v)
        results.append({"name": name, "expect": f"FAIL {rule} '{sub}'", "ok": hit, "violations": v})
    return results
