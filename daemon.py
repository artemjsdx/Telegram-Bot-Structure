import os, sys

ROOT = os.path.dirname(os.path.abspath(__file__))
os.chdir(ROOT)

pid = os.fork()
if pid > 0:
    print('BOT_PID=' + str(pid))
    sys.exit(0)

os.setsid()

pid2 = os.fork()
if pid2 > 0:
    sys.exit(0)

log = open(os.path.join(ROOT, 'bot_run.log'), 'w')
os.dup2(log.fileno(), 1)
os.dup2(log.fileno(), 2)

os.execvp('python3', ['python3', 'structure.py'])
