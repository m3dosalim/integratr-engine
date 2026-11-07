# How the Engine shell works

Read this top to bottom. It follows one Pipe from process start to a spend lookup.

LiteLLM is a separate program. It is the Gateway (one URL for many providers), the Control (keys, budgets, rate limits), and the Monitor (spend logs). This shell does not do those jobs. It asks LiteLLM to do them, and it remembers which Pipe owns which key.

A Pipe's life is: the process starts and creates one team, an admin makes a one-time token, the Pipe registers and receives a key, the Pipe says it is ready, the shell polls its health, an admin can disable it or remove it, and an admin can read its spend. The files below are those moments, in that order. `registration_store.py` is the notebook every step writes in. `main.py` is the front door that calls the others.

## settings.py

This file reads the environment and stops the process if a required value is missing. The required values are the database URL, the address where this shell calls LiteLLM, the public Engine URL that a Pipe will use for model calls, LiteLLM's master key, and the admin token.

It exists so the shell never starts half-configured. Budgets do not work without a database, and a Pipe must never receive the master key. Those two facts are enforced here, before any request arrives.

It comes first. Every later file receives the values this one already checked. `database.py` uses the database URL. `ensure_team.py` and `litellm_client.py` use the LiteLLM address and the master key. `register_pipe.py` returns the public Engine URL. `main.py` compares the admin token.

## database.py

This file opens Postgres and creates two Integratr tables in their own schema: install tokens, and one row per Pipe. LiteLLM uses the same database for its own tables. This file does not touch those.

It exists because a registration has to survive a restart. The token hash, the virtual key, the model list, the budget, and the health address live here.

It runs once, right after settings are loaded, and before any Pipe can register. `registration_store.py` is the only file that reads and writes these tables afterward.

## model_aliases.py

This file is a list of five names: `chat-default`, `image-default`, `embed-default`, `speech-default`, and `transcribe-default`.

It exists so a Pipe asks for a job, not for a provider model. The real provider names and keys stay in the LiteLLM config, which is the Gateway. This list is the shell's copy of those names.

`ensure_team.py` gives the one team all five names. `check_register_body.py` rejects a Pipe that asks for any name outside this list. A Pipe's own key then gets only the names that Pipe declared.

## ensure_team.py

When the shell starts, this file asks LiteLLM whether the team `integratr` already exists. If it does not, it creates that one team and allows it to use all five aliases. It retries while the proxy is still booting.

It exists because Control in this version is one deployment, one team, and one key per Pipe inside that team. Pipes do not create teams.

It runs after the database is ready and before the web server accepts a register call. `litellm_client.py` does the actual HTTP call. `register_pipe.py` later puts every new key on this same team id.

## install_tokens.py

An admin asks for an install token. This file makes a random token, stores only a hash of it, and returns the raw token once.

It exists so a stranger cannot register a Pipe. The token is the permission slip, and it can be used one time. The database never keeps the raw token.

This happens before register. `register_pipe.py` hashes the token the Pipe sends and asks the store whether that hash is still unused. `main.py` only lets an admin create a token.

## check_register_body.py

This file reads the register body and rejects it when the shape is wrong. It checks that `engineApi` is `"1"`, that the id, name, and version are present, that every model is one of the five aliases, that the budget and rate limit are usable numbers, and that the config schema and data schema are lists of the fields the spec requires. A secret setting is not allowed to carry a default.

It exists so a bad body never reaches LiteLLM. No key is minted, and no token is spent, if this check fails.

`register_pipe.py` calls it as the first step of register. It uses the alias list from `model_aliases.py`. It does not talk to the database or to LiteLLM.

## register_pipe.py

This is the register action, in order. It checks the body. It checks that the install token exists and is unused. It checks that the Pipe id is not already taken. It asks LiteLLM for one virtual key whose model list, budget, and rate limit come from that request. It then, in one write, marks the token used and stores the registration row. It returns the public Engine URL and the key. That is the only time the key is sent back.

The new row starts inactive. Health is unknown. The Pipe's own config values are not stored.

It exists because this is the moment a Pipe inherits Control. After this, model calls use that key against LiteLLM, and LiteLLM enforces the budget.

If the token or the id is claimed by someone else between the check and the write, this file asks LiteLLM to delete the key it just minted, and the token is not burned. `check_register_body.py` is the step before the key. `litellm_client.py` mints the key. `registration_store.py` keeps the row. `ready_pipe.py` is the next thing a Pipe does.

## litellm_client.py

This file is the only place the shell talks to LiteLLM. It looks up the team, creates the team, generates a key, deletes a key, and reads spend logs. Every call sends the master key. That key never leaves this file toward a Pipe.

It exists so Gateway, Control, and Monitor stay inside LiteLLM. Generate-key is Control. Delete-key is how spend stops. Spend-logs is Monitor. The Gateway itself is the proxy URL the Pipe calls later, with the key this file minted. This file does not send chat or image requests.

`ensure_team.py` uses the team calls at startup. `register_pipe.py` uses generate-key. `remove_pipe.py` uses delete-key. `read_spend.py` uses the spend-log call.

## bearer.py

This file takes an Authorization header and returns the token that follows the word Bearer. If the header is missing or shaped wrong, it returns an empty token.

It exists so each route does not invent its own way to read a credential.

`ready_pipe.py` uses it to read the Pipe's virtual key. `main.py` uses it to read the admin token before install-token, disable, remove, the pipe read, and the spend read.

## ready_pipe.py

The Pipe calls this after its own required settings are filled. The body carries the Pipe id and a health URL that must end in `/health`. The header must be the virtual key from register. This file loads the row, refuses the call if the Pipe is already disabled, checks the key, saves the health URL and the base address in front of it, and marks the desired state active.

It does not store the Pipe's settings. Those stay in the Pipe. It also does not decide that the process is healthy. The poller does that on the next pass.

It exists because register has no address. Until this call, the shell cannot poll health or send disable.

It comes after `register_pipe.py`. It uses `bearer.py` for the key and `registration_store.py` for the row. `health_poller.py` and `disable_pipe.py` both need the address saved here.

## health_poller.py

On a timer, this file loads every Pipe. If a Pipe has a health URL, it calls that URL. A body of ok, inactive, or degraded is stored as that state. Degraded may include a reason. Any other answer, or no answer, is stored as unreachable.

It exists so a dead process is visible. Unreachable is not the same as disabled. Disabled is an admin choice. Unreachable means the process stopped answering. The virtual key is still live either way.

It starts in `main.py` after the team exists, and it keeps running beside the web server. It reads and writes `registration_store.py`. It does not call LiteLLM.

## disable_pipe.py

An admin asks the shell to disable a Pipe. This file loads the row, requires the base address from ready, and calls that Pipe's own `/disable`. Only if the Pipe answers with success does this file mark the desired state disabled.

It exists so background work stops because the Pipe was told to stop, not because the shell only changed a label. This step does not revoke the key. A disabled Pipe's key can still spend until remove.

It comes after ready, because there is no address before that. `remove_pipe.py` is the later step that actually revokes the key. The row update goes through `registration_store.py`.

## remove_pipe.py

An admin removes a Pipe. This file loads the row, asks LiteLLM to delete that virtual key, and only then deletes the registration row. If the delete fails, the row stays, so the key can be revoked on a later try.

It exists because a row deleted while the key is still live is still a way to spend money. Revoke is first. The shell does not delete the Pipe's own data, because it never stored that data.

It is the last change to a Pipe's identity. It uses `litellm_client.py` for the revoke and `registration_store.py` for the delete. After this, `read_spend.py` can no longer find the Pipe.

## read_spend.py

An admin asks for spend with a Pipe id and, optionally, a request id. This file loads the Pipe, asks LiteLLM for the spend logs of that Pipe's key, and keeps the rows that match. A row that names a different Pipe is dropped. When a request id was given, the row must match the id the Pipe sent or the id LiteLLM itself recorded. The raw virtual key is not included in the answer.

It exists so a failure in a Pipe and a line of spend can be joined. The shell does not keep a second copy of spend. Monitor stays in LiteLLM.

It can run any time after register, until remove deletes the row. It uses `litellm_client.py` to fetch the logs and `registration_store.py` to find the key.

## registration_store.py

This file is the notebook. It inserts a token hash, checks that a token is still unused, claims a token and inserts a Pipe in one transaction, loads a Pipe, marks it ready, marks it disabled, writes the latest health state, deletes a Pipe, and lists Pipes for the poller.

It exists so the steps above share one set of rows and do not each invent a place to save. The one transaction on register is the important rule: the token is consumed and the row is saved together, or neither happens. One lock keeps the poller and the web requests from writing at the same time.

Every file from `install_tokens.py` through `read_spend.py` calls it. It does not call them. `database.py` created the tables it uses. `main.py` builds this store once at startup and passes it in.

## main.py

This file is the front door. On startup it loads settings, opens the database, creates the tables, builds the store and the LiteLLM client, makes sure the one team exists, starts the health poll, and only then serves HTTP.

The routes are the Pipe's life, in order. An admin creates an install token. A Pipe registers. A Pipe says it is ready. An admin disables. An admin removes. An admin reads the row, including health. An admin reads spend. Admin routes check the admin token through `bearer.py`. Register is authorized by the install token in the body. Ready is authorized by the virtual key.

It exists so the order is visible in one place. The work itself stays in the files above. If you are explaining the Engine, start here to see the sequence, then drop into the one file for the step you are on.
