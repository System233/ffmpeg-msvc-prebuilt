import { releasesIndex } from '../../.vitepress/generated/releases-index'

export default {
  paths() {
    return releasesIndex.map(r => ({ params: { id: r.id } }))
  }
}
