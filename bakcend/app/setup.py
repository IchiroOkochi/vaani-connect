import nltk


def download_nltk_assets() -> None:
    nltk.download("punkt")


if __name__ == "__main__":
    download_nltk_assets()
    print("Downloaded NLTK punkt.")
