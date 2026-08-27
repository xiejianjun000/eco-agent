import { ZhejiangRules } from "./zhejiang/rules"

interface ProvincePackage {
  code: string
  name: string
  rules: any[]
}

const registry: Record<string, ProvincePackage> = {
  zhejiang: {
    code: "zhejiang",
    name: "浙江省",
    rules: ZhejiangRules
  }
}

export class ProvincialRegistry {
  load(code: string): any {
    const pkg = registry[code]
    if (!pkg) {
      console.warn(`[eia-review] Province ${code} not found, using national rules only`)
      return {
        review: async () => ({ issues: [], score: 100 })
      }
    }

    return {
      review: async (doc: any, context: any) => {
        const issues = []
        for (const rule of pkg.rules) {
          try {
            const result = rule.check(doc, context)
            if (!result.passed) {
              issues.push({
                id: rule.id,
                category: rule.category,
                severity: rule.severity,
                name: rule.name,
                description: rule.description,
                detail: result.detail,
                location: result.location,
                basis: rule.basis,
                confidence: 0.88,
                level: "provincial"
              })
            }
          } catch (e) {
            console.error(`[ProvincialRegistry] Rule ${rule.id} failed:`, e)
          }
        }

        const score = Math.max(0, 100 - issues.filter((i: any) => i.severity === "critical").length * 15
                                - issues.filter((i: any) => i.severity === "major").length * 5)
        return { issues, score }
      }
    }
  }

  listProvinces(): string[] {
    return Object.keys(registry)
  }
}
