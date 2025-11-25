;; ESP32 (STR365 IO)

(def power-on  1)
(def power-off 0)

; Define pins
(def pin-power-can 0) ; ESP IO0 / pin #18
(def pin-power-n2k 1) ; ESP IO0 / pin #19

(defun set-mode-output (pin) {
    (gpio-configure pin 'pin-mode-out)
    (gpio-write pin power-off)
})

(defun set-power-state (pin power) {
    (gpio-write pin power)
})

; Setup pins for power output (and make sure they are off)
(set-mode-output pin-power-can)
(set-mode-output pin-power-n2k)

; Start CAN bus
(set-power-state pin-power-can power-on)
; Stop N2K bus
(set-power-state pin-power-n2k power-off)

; EOF