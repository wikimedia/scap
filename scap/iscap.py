#!/usr/bin/env python2
"""
Interactive deployment shell
"""
from __future__ import unicode_literals
from prompt_toolkit.shortcuts import get_input
from prompt_toolkit.filters import Always
from prompt_toolkit.history import FileHistory
from pygments.token import Token
from context import ShellContextManager
from pygments.lexers.shell import BashLexer
#import pexpect
import ui
#import click
import os
import shlex
import sys
import tmuxp

sys.path.append(os.getcwd())

class LogStreamWrapper(object):
    def __init__(self, stream, delimiter='\r'):
        self.stream = stream
        self.data = []
        self.delimiter = delimiter

    def write(self, data):
        self.data.append(data)
        #self.stream.write(data)
        #self.stream.flush()

    @property
    def num_lines(self):
        return len(self.data)

    @property
    def lastline(self):
        if len(self.data) > 0:
            return self.data[-1]
        else:
            return ""

    def __getattr__(self, attr):
       return getattr(self.stream, attr)


def main():
    #orig_stderr = sys.stderr
    #stderr_wrapper = LogStreamWrapper(orig_stderr)
    #sys.stderr = stderr_wrapper
    with ShellContextManager() as context:
        def toolbar_token_callback(cli):
            tokens = ui.get_toolbar_tokens(context)
            tokens.append((Token.Text, " | "))
            #tokens.append((Token.Text, repr(stderr_wrapper.num_lines)))
            #tokens.append((Token.Text, stderr_wrapper.lastline))
            return tokens

        def prompt_token_callback(cli):
            return ui.get_prompt_tokens(context)

        if not 'TMUX' in os.environ:
            tmux = tmuxp.Server();
            #print(tmux.attached_sessions())
            if tmux.has_session('iscap'):
                print ('error: iscap session already running. Try reattaching with `tmux attach`')
                exit(1)
            script = os.path.realpath(sys.argv[0])
            scap_root = os.path.dirname(os.path.dirname(script))
            reattach = os.path.join(scap_root,'bin','iscap-reattach')
            print scap_root
            os.execlp(reattach,scap_root,scap_root)

        tmux = tmuxp.Server();
        if tmux.has_session('iscap'):
            #args = ('attach','-t','iscap')
            #os.execvp('tmux', args)
            #session = tmux.new_session(session_name="iscap", attach_if_exists=True)
            session = tmux.findWhere({'session_name': 'iscap'})
            #tmux.attach_session(session)
        else:
            session = tmux.new_session(session_name="iscap", attach_if_exists=True)
            win = session.new_window(attach=False)
            win = session.new_window(attach=False)

        history_file = FileHistory(os.path.expanduser('~/.iscap_history'))

        while True:
            cmd = get_input(get_prompt_tokens=prompt_token_callback,
                             get_bottom_toolbar_tokens=toolbar_token_callback,
                             enable_system_bindings=Always(),
                             history=history_file,
                             lexer=BashLexer, style=ui.ScapStyle
                             )
            if len(cmd) > 0:
                try:
                    cmd = context.execute(cmd)
                    if cmd.value == "exit":
                        session.kill_session()
                    elif cmd.value == "detach":
                        tmux.cmd("detach-client")
                    else:
                        print cmd
                        #tmux.cmd(cmd.value())
                finally:
                    pass


if __name__ == '__main__':
    main()