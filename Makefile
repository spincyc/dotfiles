SHELL := /bin/sh

ARCH_PACKAGES := \
  curl \
  git \
  make \
  nodejs \
  python \
  ripgrep \
  sqlite \
  tmux \
  zsh

.PHONY: install-packages sanity-check verify

install-packages:
	sudo pacman -S --needed -- $(ARCH_PACKAGES)

sanity-check:
	./tools/sanity-check

verify: sanity-check
	./tools/verify
