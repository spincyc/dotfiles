;;; .emacs --- Portable Emacs configuration -*- lexical-binding: t; -*-

;;; Appearance

(custom-set-faces
 '(default ((t (:family "Monospace"
                :height 100
                :background "black"
                :foreground "white"))))
 '(bold ((t (:weight normal))))
 '(underline ((t (:underline nil))))
 '(font-lock-type-face ((t (:foreground "steelblue3"))))
 '(font-lock-string-face ((t (:foreground "green4"))))
 '(font-lock-keyword-face ((t (:foreground "red4"))))
 '(font-lock-comment-face ((t (:foreground "gold"))))
 '(font-lock-builtin-face ((t (:foreground "red3"))))
 '(font-lock-constant-face ((t (:foreground "red3"))))
 '(font-lock-preprocessor-face ((t (:foreground "darkorange"))))
 '(font-lock-variable-name-face ((t (:foreground "magenta4"))))
 '(font-lock-function-name-face ((t (:foreground "brown4")))))

(when (fboundp 'tool-bar-mode)
  (tool-bar-mode -1))

;;; Interface behavior

(setq inhibit-startup-screen t
      make-backup-files nil
      ring-bell-function #'ignore
      use-short-answers t)

(line-number-mode 1)
(column-number-mode 1)
(setq display-time-day-and-date t)
(display-time-mode 1)

(setq-default indent-tabs-mode nil
              truncate-lines t)

;; Let display-buffer reuse a window on any frame when possible.
(add-to-list 'display-buffer-alist
             '("\\`.*\\'" nil (reusable-frames . t)))

;;; Navigation and commands

(global-set-key (kbd "<C-tab>") #'next-multiframe-window)
(global-set-key (kbd "<C-S-iso-lefttab>") #'previous-multiframe-window)
(global-set-key (kbd "<f8>") #'compile)
(global-set-key (kbd "M-g") #'goto-line)

;;; File types and indentation

(dolist (mapping '(("\\.h\\'" . c++-mode)
                   ("\\.cc\\'" . c++-mode)
                   ("\\.def\\'" . c++-mode)
                   ("\\.mk\\." . makefile-gmake-mode)))
  (add-to-list 'auto-mode-alist mapping))

(defun dotfiles-c-style ()
  "Apply the preferred four-space C and C++ style."
  (c-set-style "ellemtel")
  (setq-local c-basic-offset 4)
  (c-set-offset 'access-label -2)
  (c-set-offset 'innamespace 4)
  (c-set-offset 'arglist-close 'c-lineup-close-paren))

(add-hook 'c-mode-common-hook #'dotfiles-c-style)

;;; Optional local packages

(declare-function toggle-source "toggle-source" ())
(declare-function p4-menu-add "p4" ())

(dolist (directory '("~/emacs/lua"
                     "~/emacs/toggle"
                     "~/emacs/p4"))
  (let ((expanded-directory (expand-file-name directory)))
    (when (file-directory-p expanded-directory)
      (add-to-list 'load-path expanded-directory))))

(cond
 ((and (fboundp 'treesit-ready-p)
       (treesit-ready-p 'lua t))
  (add-to-list 'auto-mode-alist '("\\.lua\\'" . lua-ts-mode)))
 ((locate-library "lua-mode")
  (autoload 'lua-mode "lua-mode" "Major mode for editing Lua." t)
  (add-to-list 'auto-mode-alist '("\\.lua\\'" . lua-mode))))

(when (require 'toggle-source nil t)
  (global-set-key (kbd "<f11>") #'toggle-source))

(when (require 'p4 nil t)
  (when (fboundp 'p4-menu-add)
    (p4-menu-add)))

;;; Machine-local configuration

(let ((local-config (expand-file-name "~/.emacs.local")))
  (when (file-readable-p local-config)
    (load local-config nil t)))

;;; .emacs ends here
