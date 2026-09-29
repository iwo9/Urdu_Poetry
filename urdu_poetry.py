"""
Entry point for the Urdu Poetry app. Run this to prepare today's poem.

For now this just runs the web-scraping step and prints the result.
Translation, transliteration, commentary generation, and the nicer
line-by-line display will be added on top of this as we build them out.
"""

import webscrapping


def prepare_daily_poem():
    ghazal = webscrapping.get_random_ghazal()
    return ghazal


def main():
    ghazal = prepare_daily_poem()
    webscrapping.print_ghazal(ghazal)


if __name__ == "__main__":
    main()
