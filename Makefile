# Core2 Claude usage dashboard — run `make` for the list of targets.

PORT  ?= $(firstword $(wildcard /dev/cu.wchusbserial* /dev/cu.usbserial*))
# the Core2's CH9102 serial chip is unreliable at 921600
BAUD  ?= 460800

FW_VERSION ?= 2.5.3
FW_URL     ?= https://github.com/m5stack/uiflow-micropython/releases/download/2.5.3/uiflow-50e4407-esp32-spiram-16mb-core2-v2.5.3-20260911.bin
FW_IMAGE   := firmware/uiflow2-core2-v$(FW_VERSION).bin
BACKUP     ?= firmware/factory-backup-16mb.bin

BUILD   := build
FONTS   := $(BUILD)/fonts
FONT_URL := https://github.com/JulietaUla/Montserrat/raw/master/fonts/ttf

MPREMOTE := uvx mpremote connect $(PORT)
ESPTOOL  := uvx esptool --port $(PORT) --baud $(BAUD)
SERIAL   := uv run tools/serialtool.py $(PORT)

.DEFAULT_GOAL := help
.PHONY: help deploy check logs stop reset repl ls preview firmware flash-firmware backup restore clean need-port

help: ## show this help
	@awk 'BEGIN {FS = ":.*## "} /^[a-zA-Z_-]+:.*## / {printf "  \033[36m%-15s\033[0m %s\n", $$1, $$2}' $(MAKEFILE_LIST)
	@echo "  PORT=$(or $(PORT),<none found>)"

need-port:
	@test -n "$(PORT)" || { echo "No Core2 serial port found; plug it in or pass PORT=/dev/cu.…"; exit 1; }

# --- day to day -----------------------------------------------------------------

deploy: need-port check ## upload device/ + secrets from .env, set autostart, reset
	uv run deploy.py --port $(PORT)

check: ## syntax-check the device code
	@python3 -c "import ast,sys; [ast.parse(open(f).read(), f) for f in sys.argv[1:]]" device/*.py && echo "device code OK"

logs: need-port ## follow the device console (Ctrl-C to quit)
	$(SERIAL) monitor

stop: need-port ## interrupt the dashboard, leaving a MicroPython REPL
	$(SERIAL) stop

reset: need-port ## restart the board (dashboard autostarts)
	$(SERIAL) stop
	$(MPREMOTE) resume reset

repl: need-port stop ## interactive REPL (Ctrl-] to exit; `make reset` to restart the dashboard)
	$(MPREMOTE) resume repl

ls: need-port stop ## list files on the device
	$(MPREMOTE) resume fs ls /flash
	$(MPREMOTE) resume reset

preview: $(FONTS)/Montserrat-Regular.ttf $(FONTS)/Montserrat-SemiBold.ttf ## render the three screens to build/preview/*.png with live data
	@mkdir -p $(BUILD)/preview
	uv run tools/preview.py $(BUILD)/preview $(FONTS)

$(FONTS)/%.ttf:
	@mkdir -p $(FONTS)
	curl -sfL -o $@ $(FONT_URL)/$*.ttf

# --- firmware (these rewrite the whole 16 MB flash) ------------------------------

firmware: $(FW_IMAGE) ## download the UIFlow2 MicroPython image

$(FW_IMAGE):
	@mkdir -p firmware
	curl -fL -o $@ $(FW_URL)

flash-firmware: need-port $(FW_IMAGE) ## erase the board and install UIFlow2 (then run `make deploy`)
	@read -p "Overwrite ALL flash on $(PORT) with UIFlow2 $(FW_VERSION)? [y/N] " a && [ "$$a" = y ]
	$(ESPTOOL) write-flash 0 $(FW_IMAGE)

backup: need-port ## dump the full 16 MB flash to BACKUP (default firmware/factory-backup-16mb.bin, ~7 min)
	@test ! -e $(BACKUP) || { echo "$(BACKUP) exists; pass BACKUP=other.bin"; exit 1; }
	$(ESPTOOL) read-flash 0 0x1000000 $(BACKUP)

restore: need-port ## write BACKUP back to the board (default: the original factory firmware)
	@read -p "Overwrite ALL flash on $(PORT) with $(BACKUP)? [y/N] " a && [ "$$a" = y ]
	$(ESPTOOL) write-flash 0 $(BACKUP)

clean: ## remove build/ (previews, fonts)
	rm -rf $(BUILD)
