import sharp from 'sharp'
import { readFileSync } from 'fs'
import { fileURLToPath } from 'url'
import { dirname, join } from 'path'

const __filename = fileURLToPath(import.meta.url)
const __dirname = dirname(__filename)

const svgPath = join(__dirname, '../public/icon.svg')
const outputDir = join(__dirname, '../public')

const sizes = [
  { name: 'pwa-192x192.png', size: 192 },
  { name: 'pwa-512x512.png', size: 512 },
  { name: 'apple-touch-icon.png', size: 180 },
  { name: 'favicon.ico', size: 32 }
]

async function generateIcons() {
  const svgBuffer = readFileSync(svgPath)

  for (const { name, size } of sizes) {
    const outputPath = join(outputDir, name)

    try {
      await sharp(svgBuffer)
        .resize(size, size)
        .png()
        .toFile(outputPath)

      console.log(`✓ Generated ${name} (${size}x${size})`)
    } catch (error) {
      console.error(`✗ Failed to generate ${name}:`, error.message)
    }
  }

  console.log('\n✨ Icon generation complete!')
}

generateIcons().catch(console.error)
