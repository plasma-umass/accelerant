# Optastic

## Setup

1. Git clone
2. Make and activate virtualenv
3. Install from `requirements.txt`

## Basic usage

In one terminal, activate the virtualenv and run

```console
$ flask --app=optastic_server run
```

In another terminal, run

```console
$ curl 'http://127.0.0.1:5000/optimize?project=PATH_TO_PROJECT_ROOT&filename=RELATIVE_PATH_TO_FILE_IN_PROJECT&line=LINE_NUMBER_IN_FILE'
```
