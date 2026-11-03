.PHONY: cli mail-up mail-down send-mail

SUBJECT ?= Test message
BODY ?= Test body

cli:
	PYDANTIC_AI_NO_BANNER=1 uv run cli

mail-up:
	docker compose up -d --wait

mail-down:
	docker compose down

# make send-mail TO=<address> [SUBJECT=...] [BODY=...] [ATTACH=<path>] [REPLY_TO='<message-id>']
send-mail:
	@uv run python scripts/send_mail.py --to "$(TO)" --subject "$(SUBJECT)" --body "$(BODY)" \
		$(if $(ATTACH),--attach "$(ATTACH)") $(if $(REPLY_TO),--reply-to "$(REPLY_TO)")
