### Server Setup

Poetry is used for dependency management, first install it:
`curl -sSL https://install.python-poetry.org | python3 -`

Add it to PATH:
`export PATH="$HOME/.local/bin:$PATH"`

Install the server project's dependencies:
`cd app/server && poetry install`

To make VSCode use the virtualenv created by Poetry, add it in VSCode by clicking "Python" and then "Enter Interpreter Path".