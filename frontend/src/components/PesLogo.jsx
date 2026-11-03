import logo from '../assets/brand/pes-university-logo.png'
import { cx } from './ui.jsx'

/**
 * Official PES University logo (unaltered PNG with its own transparency, 400x193).
 * Its lettering is navy, so it must sit on a light background (white card, header):
 * never directly on the navy sidebar or overlay. Height is set by the caller; the
 * width follows the original aspect ratio.
 */
export default function PesLogo({ className }) {
  return <img src={logo} alt="PES University" width={400} height={193} className={cx('w-auto select-none', className)} draggable={false} />
}
