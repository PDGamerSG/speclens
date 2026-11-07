/** Fast feedback before uploading; the server independently validates decoded photos. */
export function photoError(file: File): string | null {
  if (!file.size) return 'This photo is empty. Choose a JPG, PNG or WebP image.'
  if (file.size > 8 * 1024 * 1024) return 'Choose an image smaller than 8 MB.'
  const supported = ['image/jpeg', 'image/png', 'image/webp']
  if (file.type ? !supported.includes(file.type) : !/\.(jpe?g|png|webp)$/i.test(file.name)) {
    return 'Choose a JPG, PNG or WebP still photo.'
  }
  return null
}
