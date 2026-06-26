import { cleanup } from '@testing-library/react'
import { afterEach } from 'vitest'

// jest-dom matchers (.toBeInTheDocument, etc.) + their vitest type augmentation.
import '@testing-library/jest-dom/vitest'

// Unmount between tests without relying on Vitest globals being enabled.
afterEach(() => {
  cleanup()
})
