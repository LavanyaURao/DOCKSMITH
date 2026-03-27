import os, re, subprocess, stat

def run_in_container(rootfs, command, env, workdir="/", extra_env=None):
    if not command:
        raise ValueError("No command to run")
    container_env = dict(env)
    if extra_env:
        container_env.update(extra_env)
    if "PATH" not in container_env:
        container_env["PATH"] = "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
    workdir = workdir or "/"
    for d in ["proc", "dev", "tmp", "etc"]:
        os.makedirs(os.path.join(rootfs, d), exist_ok=True)
    for bd in ["bin","usr/bin","usr/local/bin","sbin","usr/sbin","lib","usr/lib"]:
        bp = os.path.join(rootfs, bd)
        if not os.path.isdir(bp): continue
        for r, dirs, files in os.walk(bp):
            for fn in files:
                fp = os.path.join(r, fn)
                if os.path.islink(fp): continue
                try:
                    st = os.stat(fp)
                    if st.st_mode & stat.S_IRUSR:
                        os.chmod(fp, st.st_mode | 0o111)
                except: continue
    env_lines = "\n".join(f"export {k}='{v}'" for k,v in sorted(container_env.items()) if re.match(r'^[A-Za-z_]\w*$', k))
    inner = command[0] if len(command)==1 else " ".join(f"'{a}'" for a in command)
    script = os.path.join(rootfs, ".docksmith_run.sh")
    with open(script,"w") as f:
        f.write(f"#!/bin/sh\n{env_lines}\ncd '{workdir}' 2>/dev/null || cd /\n{inner}\n")
    os.chmod(script, 0o755)
    try:
        return subprocess.run(["chroot", rootfs, "/bin/sh", "/.docksmith_run.sh"], env={"PATH":"/usr/sbin:/usr/bin:/sbin:/bin"}).returncode
    finally:
        try: os.remove(script)
        except: pass
