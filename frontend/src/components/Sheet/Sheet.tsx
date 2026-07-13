import type { ReactNode } from 'react'
import { Dialog, Heading, Modal, ModalOverlay } from 'react-aria-components'

import * as styles from './Sheet.css'

export type SheetProps = {
  isOpen: boolean
  /** Called when the sheet is dismissed (Done, Escape, or scrim click). */
  onClose: () => void
  /** Visible, centered title — also the dialog's accessible name. */
  title: string
  /** Optional left-aligned Back affordance (e.g. to a parent sheet). */
  onBack?: () => void
  children: ReactNode
}

/**
 * One concern per sheet (home-curation spec §5). The chrome is deliberately
 * quiet — a Back/Done header, no busy toolbar — and all the modal behaviour is
 * delegated to React Aria so it is correct by construction.
 */
export function Sheet({ isOpen, onClose, title, onBack, children }: SheetProps) {
  return (
    <ModalOverlay
      className={styles.overlay}
      isOpen={isOpen}
      onOpenChange={(open) => {
        if (!open) onClose()
      }}
      isDismissable
    >
      <Modal className={styles.sheet}>
        <Dialog className={styles.dialog}>
          <div className={styles.header}>
            {onBack ? (
              <button type="button" className={styles.headerButton} onClick={onBack}>
                Back
              </button>
            ) : null}
            <Heading slot="title" className={styles.title}>
              {title}
            </Heading>
            <button type="button" className={styles.headerButton} onClick={onClose}>
              Done
            </button>
          </div>
          {/* The ONLY scrollable region (C1): content taller than the capped
              sheet scrolls here while the Back/Done header above stays pinned
              and reachable. */}
          <div className={styles.body}>{children}</div>
        </Dialog>
      </Modal>
    </ModalOverlay>
  )
}
