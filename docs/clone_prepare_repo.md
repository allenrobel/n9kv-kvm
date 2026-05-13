# Clone and Prepare the n9kv-kvm Repository

The scripts and environment vars in this repository assume it is cloned into
the following location.  You can, of course, put it wherever you want, but
will need to update everything to match your preferred location.

<!-- pyml disable-next-line commands-show-output -->
```text
$HOME/repos/n9kv-kvm
```

```bash
mkdir $HOME/repos
cd $HOME/repos
git clone https://github.com/allenrobel/n9kv-kvm.git
cd n9kv-kvm
```

## Create Python Virtual Environment

So that this project's dependencies don't interfere with other projects,
it's recommended to create and activate a Python venv.

```bash
cd $HOME/repos/n9kv-kvm
python3.13 -m venv .venv --prompt n9kv-kvm
source $HOME/repos/n9kv-kvm/.venv/bin/activate
source $HOME/repos/n9kv-kvm/env/env.sh
```

## Upgrade pip and install uv

```bash
source $HOME/repos/n9kv-kvm/.venv/bin/activate
source $HOME/repos/n9kv-kvm/env/env.sh
pip install --upgrade pip
pip install uv
```

If you see a message similar to the below, check your PYTHONPATH and
ensure that `$HOME/repos/n9kv-kvm/.venv` is the first entry.

```bash
  Attempting uninstall: pip
    Found existing installation: pip 24.0
    Not uninstalling pip at /home/arobel/py311/lib/python3.11/site-packages, outside environment /home/arobel/repos/n9kv-kvm/.venv
    Can't uninstall 'pip'. No files were found to uninstall.

```

The above should not happen if you `source $HOME/repos/n9kv-kvm/env/env.sh` since this
sets PYTHONPATH, among other things.

For example, PYTHONPATH should look like below (at least the first entry).

```bash
(.venv) arobel@cvd-3:~/repos/n9kv-kvm$ echo $PYTHONPATH
/home/arobel/repos/n9kv-kvm/.venv
(.venv) arobel@cvd-3:~/repos/n9kv-kvm$
```

If it doesn't, then do the following:

```bash
export PYTHONPATH=$HOME/repos/n9kv-kvm/.venv:$PYTHONPATH
# And try to upgrade pip and install uv again
source $HOME/repos/n9kv-kvm/.venv/bin/activate
pip install --upgrade pip
pip install uv
```

## uv Dependency Tree

When you run `uv sync` in the next section the following dependencies will be installed.

```bash
(n9kv-kvm) arobel@Allen-M4 n9kv-kvm % uv tree
Resolved 34 packages in 9ms
n9kv-kvm v0.1.0
├── ansible v11.8.0
│   └── ansible-core v2.18.7
│       ├── cryptography v45.0.5
│       │   └── cffi v1.17.1
│       │       └── pycparser v2.22
│       ├── jinja2 v3.1.6
│       │   └── markupsafe v3.0.2
│       ├── packaging v25.0
│       ├── pyyaml v6.0.2
│       └── resolvelib v1.0.1
├── black v25.1.0
│   ├── click v8.2.1
│   ├── mypy-extensions v1.1.0
│   ├── packaging v25.0
│   ├── pathspec v0.12.1
│   └── platformdirs v4.3.8
├── flake8 v7.3.0
│   ├── mccabe v0.7.0
│   ├── pycodestyle v2.14.0
│   └── pyflakes v3.4.0
├── isort v6.0.1
├── mypy v1.17.1
│   ├── mypy-extensions v1.1.0
│   ├── pathspec v0.12.1
│   └── typing-extensions v4.14.1
├── pylint v3.3.8
│   ├── astroid v3.3.11
│   ├── dill v0.4.0
│   ├── isort v6.0.1
│   ├── mccabe v0.7.0
│   ├── platformdirs v4.3.8
│   └── tomlkit v0.13.3
├── requests v2.32.4
│   ├── certifi v2025.7.14
│   ├── charset-normalizer v3.4.2
│   ├── idna v3.10
│   └── urllib3 v2.5.0
└── types-pyyaml v6.0.12.20250809
(n9kv-kvm) arobel@Allen-M4 n9kv-kvm %
```

## Run `uv sync` to Install Dependencies

To install dependencies used in this repository, do the following.

```bash
source $HOME/repos/n9kv-kvm/.venv/bin/activate
source $HOME/repos/n9kv-kvm/env/env.sh
cd $HOME/repos/n9kv-kvm
uv sync
```

## Test the Environment

Test ansible-playbook to see if it's properly installed

```bash
source $HOME/repos/n9kv-kvm/.venv/bin/activate
ansible-playbook --version
# whereis should show $HOME/repos/n9kv-kvm/.venv/bin/ansible-playbook
whereis ansible-playbook
```

If ansible-playbook shows a different path, then your `PYTHONPATH` environment
variable contains a path to a different `ansible-playbook` that is overriding
the local installation path.  This may be OK if you prefer to use the other
version.  Else, modify your `PYTHONPATH` accordingly, e.g.:

```bash
unset PYTHONPATH
export PYTHONPATH=$HOME/repos/n9kv-kvm/.venv:$PYTHONPATH
```
