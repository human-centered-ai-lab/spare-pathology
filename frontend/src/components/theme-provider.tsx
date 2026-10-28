import { useEffect, useState } from "react"
import type { ReactNode } from "react"
import type { Theme } from "@/components/theme-context"
import { ThemeContext } from "@/components/theme-context"

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [theme, setTheme] = useState<Theme>(() => {
    if (typeof window !== "undefined") {
      return (localStorage.getItem("spare-theme") as Theme)
        || (localStorage.getItem("syneval-theme") as Theme)
        || "system"
    }
    return "system"
  })

  useEffect(() => {
    const root = window.document.documentElement
    root.classList.remove("light", "dark")

    if (theme === "system") {
      const systemTheme = window.matchMedia("(prefers-color-scheme: dark)").matches
        ? "dark"
        : "light"
      root.classList.add(systemTheme)
    } else {
      root.classList.add(theme)
    }

    localStorage.setItem("spare-theme", theme)
    localStorage.removeItem("syneval-theme")
  }, [theme])

  return (
    <ThemeContext.Provider value={{ theme, setTheme }}>
      {children}
    </ThemeContext.Provider>
  )
}
