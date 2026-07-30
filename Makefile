SHELL := /bin/sh

ARCH_PACKAGES := \
  curl \
  git \
  make \
  nodejs \
  python \
  ripgrep \
  tmux \
  zsh

.PHONY: install-packages sanity-check verify verify-guidance

install-packages:
	sudo pacman -S --needed -- $(ARCH_PACKAGES)

sanity-check:
	./tools/sanity-check

verify: sanity-check
	./tools/verify

verify-guidance:
	./tools/verify --only bootstrap_budget bootstrap_files guidance_crossrefs \
	  guidance_index core_recovery_contract
