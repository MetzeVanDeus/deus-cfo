import '@testing-library/jest-dom/vitest'
import { afterEach } from 'vitest'
import { cleanup } from '@testing-library/react'
import { api } from '../../src/lib/helpers'

afterEach(() => {
  cleanup()
  delete api.defaults.adapter
  localStorage.clear()
})
