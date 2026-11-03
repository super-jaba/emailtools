# emailtool

Chat with an AI agent about emails you send it. Each run is one chat session
with its own mailbox address; nothing persists between runs.

## Usage

1. Copy `.env.example` to `.env` and set the LLM settings.
2. Start the dev mail server: `make mail-up`.
3. Start the chat: `make cli`. It prints the session address.
4. Send mail to that address from another shell:
   `make send-mail TO=<address> SUBJECT="Hello" BODY="..." [ATTACH=<path>]`
5. Ask the agent about it, e.g. "what's in my inbox?".
