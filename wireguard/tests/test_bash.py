from utils.bash import Bash

def test_bash_echo():
    out = Bash.run(["echo", "hello"])
    assert out == "hello"
