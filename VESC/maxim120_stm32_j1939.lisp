;; STM32 (Maxim_120)

(def power-on  1)
(def power-off 0)

; +12V AUX output (on pins #17 and #30)
(def aux-power-cooling 1) ; AUX1 will be used for cooling

(set-aux aux-power-cooling power-off) ; Set AUX1 to OFF


; J1939 related functions
(defun send-ET1 () {      ; ENGINE TEMPERATURE #1: ET1 (every 1s)
    (def vesc-sa   0x01)  ; VESC Source Address (main ECU: 0x01)
    (def pgn     0xFEEE)  ; 65262
    (def priority     6)

    ; Byte #1: SPN 110: Engine coolant temperature (-40 to 210°C, 1°C/bit)
    (def temp-coolant (+ (get-temp-fet) 40))   ; TODO: get motor temp (instead of VESC temp)
    ; Byte #2: SPN 174: Engine fuel temperature #1 (-40 to 210°C, 1°C/bit)
    ; 23°C => 63 => 0x3F
    ; Bytes #3 & #4: SPN  175: Engine oil temperature #1 (-273 to 1735°C, 0.03125°C/bit => x 32)
    ; 45°C => 1713 => 0x06B1 => 0xB1 0x06

    (def eid 0x00000000u32)
    (def eid (bits-enc-int eid 0 vesc-sa 8))
    (def eid (bits-enc-int eid 8 pgn 18))
    (def eid (bits-enc-int eid 26 priority 3))

    (def data (list (bits-enc-int 0x00 0 temp-coolant 8) 0x3F 0xB1 0x06 0xFF 0xFF 0xFF 0xFF))
    (can-send-eid eid data)
})

(defun send-EEC1 () {     ; ELECTRONIC ENGINE CONTROLLER #1: EEC1 (every 100 ms)
    (def vesc-sa   0x01)  ; VESC Source Address (main ECU: 0x01)
    (def pgn     0xF004)  ; 61444
    (def priority     3)

    ; Byte #2: SPN 512: Driver's demand percent torque (-125% to 125% 1%/bit)
    ; Byte #3: SPN 513: Actual engine percent torque   (-125% to 125% 1%/bit)

    ; Bytes #4 and #5: SPN 190: Engine speed (RPM) (0.125 rpm per bit => x 8)
    (def rpm 1234)        ; TODO: get real motor rpm
    (def rpm (* rpm 8))   ;
    ; 1234 => 9872 => 0x2690 => 0x90 0x26 (LSB)

    (def eid 0x00000000u32)
    (def eid (bits-enc-int eid 0 vesc-sa 8))
    (def eid (bits-enc-int eid 8 pgn 18))
    (def eid (bits-enc-int eid 26 priority 3))

    (def data (list 0xFF 0xFF 0xFF 0x90 0x26 0xFF 0xFF 0xFF))
    (can-send-eid eid data)
})

(defun send-EEC2 () {     ; ELECTRONIC ENGINE CONTROLLER #2: EEC2 (every 50 ms)
    (def vesc-sa   0x01)  ; VESC Source Address (main ECU: 0x01)
    (def pgn     0xF003)  ; 61443
    (def priority     3)

    ; Byte #3: SPN 93: Engine Percent Load (0% to 125% 1%/bit)
    ; 45% => 45 => 0x2D

    (def eid 0x00000000u32)
    (def eid (bits-enc-int eid 0 vesc-sa 8))
    (def eid (bits-enc-int eid 8 pgn 18))
    (def eid (bits-enc-int eid 26 priority 3))

    (def data (list 0xFF 0xFF 0x2D 0xFF 0xFF 0xFF 0xFF 0xFF))
    (can-send-eid eid data)
})

(defun send-EEC4 () {     ; ELECTRONIC ENGINE CONTROLLER #4: EEC4 (on request)
    (def vesc-sa   0x01)  ; VESC Source Address (main ECU: 0x01)
    (def pgn     0xFEBE)  ; 65214
    (def priority     7)

    ; Bytes #1 & #2: SPN 166: Engine rated power (0.5 kW/bit => x 2)
    ; 20 kW => 40 => 0x0028 => 0x28 0x00

    ; Bytes #3 & #4: SPN 189: Engine rated RPM   (0.125 rpm/bit => x 8)
    ; 3500 rpm => 14000 => 0x000036B0 => 0xB0 0x36 0x00 0x00 (LSB)

    (def eid 0x00000000u32)
    (def eid (bits-enc-int eid 0 vesc-sa 8))
    (def eid (bits-enc-int eid 8 pgn 18))
    (def eid (bits-enc-int eid 26 priority 3))

    (def data (list 0x28 0x00 0xB0 0x36 0x00 0x00 0x00 0x00 ))
    (can-send-eid eid data)
})

(defun send-EFL () {      ; ENGINE FLUID LEVEL/PRESSURE (every 0.5 s)
    (def vesc-sa   0x01)  ; VESC Source Address (main ECU: 0x01)
    (def pgn     0xFEEF)  ; 65263
    (def priority     6)

    ; Byte #1: SPN 94: Fuel delivery pressure (4 kPa/bit => / 4)
    ; 2 bar => 200 kPa => 50 => 0x32
    ; Byte #2: n/a
    ; Byte #3: SPN 98: Engine oil level (0.4 %/bit => x 2.5)
    ; Byte #4: SPN 100: Engine oil pressure (4 kPa/bit => / 4)
    ; 4 bar => 400 kPa => 100 => 0x64
    ; Bytes #5 & #6: SPN 101: Crankcase pressure (1/128kPa /bit, -250kPa)
    ; Byte #7: SPN 109: Engine coolant pressure (2 kPa/bit => / 2)
    ; 3 bar => 300 kPa => 75 => 0x4B
    ; Byte #8: SPN 111: Engine coolant level (0.4 %/bit => x 2.5)

    (def eid 0x00000000u32)
    (def eid (bits-enc-int eid 0 vesc-sa 8))
    (def eid (bits-enc-int eid 8 pgn 18))
    (def eid (bits-enc-int eid 26 priority 3))

    (def data (list 0x32 0xFF 0xFF 0x64 0xFF 0xFF 0x4B 0xFF ))
    (can-send-eid eid data)
})

(defun send-FUEL () {       ; FUEL CONSUMPTION (every 1 s)
    (def vesc-sa   0x01)    ; VESC Source Address (main ECU: 0x01)
    (def pgn     0xFEE9)    ; 65257
    (def priority     6)

    ; TODO: send real data
    ; Bytes #1, #2, #3 & #4: SPN 182: Engine trip fuel (0.5kg/bit => x 2)
    ; 2 kg => 4 => 0x00000004 => 0x04 0x00 0x00 0x00 (LSB)

    ; Bytes #5, #6, #7 & #8: SPN 250: Engine total fuel used  (0.5kg/bit => x 2)
    ; 4 kg => 8 => 0x00000008 => 0x08 0x00 0x00 0x00 (LSB)

    (def eid 0x00000000u32)
    (def eid (bits-enc-int eid 0 vesc-sa 8))
    (def eid (bits-enc-int eid 8 pgn 18))
    (def eid (bits-enc-int eid 26 priority 3))

    (def data (list  0x04 0x00 0x00 0x00 0x08 0x00 0x00 0x00))
    (can-send-eid eid data)
})

(defun send-DIST () {       ; VEHICULE DISTANCE
    (def vesc-sa   0x01)    ; VESC Source Address (main ECU: 0x01)
    (def pgn     0xFEE0)    ; 65248
    (def priority     6)

    ; TODO: send real data
    ; Bytes #1, #2, #3 & #4: SPN 244: Trip distance (0.125 km/bit => x 8)
    ; 12 km => 96 => 0x00000060 => 0x60 0x00 0x00 0x00 (LSB)

    ; Bytes #5, #6, #7 & #8: SPN 245: Vehicule total distance (0.125 km/bit => x 8)
    ; 123 km => 984 => 0x000003D8 => 0xD8 0x03 0x00 0x00 (LSB)

    (def eid 0x00000000u32)
    (def eid (bits-enc-int eid 0 vesc-sa 8))
    (def eid (bits-enc-int eid 8 pgn 18))
    (def eid (bits-enc-int eid 26 priority 3))

    (def data (list 0x60 0x00 0x00 0x00 0xD8 0x03 0x00 0x00))
    (can-send-eid eid data)
})

(defun send-HOURS () {      ; ENGINE HOURS, REVOLUTIONS (on request)
    (def vesc-sa   0x01)    ; VESC Source Address (main ECU: 0x01)
    (def pgn     0xFEE5)    ; 65253
    (def priority     6)

    ; TODO: send real data
    ; Bytes #1, #2, #3 & #4: SPN 247: Total engine hours (0.05 hours/bit => x 20)
    ; 123 hours => 2460 => 0x0000099C => 0x9C 0x09 0x00 0x00 (LSB)

    ; Bytes #5, #6, #7 & #8: SPN 249: Vehicule total distance (1000r/bit => / 1000)
    ; (ignored)

    (def eid 0x00000000u32)
    (def eid (bits-enc-int eid 0 vesc-sa 8))
    (def eid (bits-enc-int eid 8 pgn 18))
    (def eid (bits-enc-int eid 26 priority 3))

    (def data (list 0x9C 0x09 0x00 0x00 0xFF 0xFF 0xFF 0xFF))
    (can-send-eid eid data)
})

; Start J1939 loops
(loopwhile-thd 100 t {
        (send-ET1)
        (send-HOURS)
        (send-FUEL)
        (sleep 1)
})

(loopwhile-thd 100 t {
        (send-EFL)
        (sleep 0.5)
})

(loopwhile-thd 100 t {
        (send-EEC1)
        (send-EEC4)
        (send-DIST)
        (sleep 0.1)
})

(loopwhile-thd 100 t {
        (send-EEC2)
        (sleep 0.05)
})

; Handler for J1939 REQUEST
(defun can-request (eid data) {
    (print "CAN EID")
    (if (= eid 0x18EAFFFE) {
        (print "CAN REQUEST")
        (if (= data 0xE9FE00)) {
            (send-FUEL)
        }
    }
    ; Save memory by freeing data when done. This can be omitted as GC
    ; will free it in the next run, but doing it prevents the memory
    ; usage from increasing more than needed.
    (free data)
    )}
)

; This function waits for events from the C code and calls the
; handlers for them when the events arrive.
(defun event-handler ()
    {(loopwhile t
        (recv
            ((event-can-eid (? id) . (? data)) (can-request id data))
            (_ nil) ; ignore other events
        )
    )}
)

; Enable the CAN event for extended ID (EID) frames
(event-enable 'event-can-eid 1)

; Spawn the event handler thread and pass the ID it returns to C
(event-register-handler (spawn 150 event-handler))

(print "END OF STARTUP")

; EOF