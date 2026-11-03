# emailtool

A demo of giving an AI agent exactly the emails it needs, and nothing more,
without mailbox integrations or permission management.

## Why

A lot of useful information arrives by email: inquiries, offers, requests.
These emails often come with attachments and a back-and-forth thread, and
an AI agent could help a lot with reading and summarizing them, or with
drafting a reply.

But giving an agent access to your whole mailbox is a big step. It could
read everything, and setting up permissions so it only sees the right
messages is tedious and easy to get wrong.

A simpler idea: you pick the emails, forward them to a temporary inbox, and
the agent sees only those. emailtool is a small demo of this idea.

## How it works

Each conversation with the agent gets its own fresh email address. Forward
any messages you want help with to that address, attachments and threads
included, and the agent can read them. The inbox exists only for that
conversation; when the chat ends, it's gone.

## Usage

1. Copy `.env.example` to `.env` and set the LLM settings.
2. Start the dev mail server: `make mail-up`.
3. Start the chat: `make cli`. It prints the session address.
4. Send mail to that address from another shell:
   `make send-mail TO=<address> SUBJECT="Hello" BODY="..." [ATTACH=<path>]`
5. Ask the agent about it, e.g. "what's in my inbox?".
