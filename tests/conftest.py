from IPython.terminal.interactiveshell import TerminalInteractiveShell


def pytest_configure():
    TerminalInteractiveShell.instance()
