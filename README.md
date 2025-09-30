# Typepad Blog Archiver & WordPress Importer 📚

A comprehensive tool to archive your entire Typepad blog and seamlessly migrate it to WordPress. Save your content, preserve your media, and move\!

## 🚀 Quick Start

### Prerequisites

**Python 3** must be installed on your system. Install required packages using the included `requirements.txt` file:

```bash
pip3 install -r requirements.txt
```

> **Windows Users:** The `python-magic-bin` package, included in `requirements.txt`, has the necessary files for Windows. If you do get errors related to libmagic.dll you should try to force reinstall:
```bash
pip3 install --force-reinstall --no-cache-dir -r requirements.txt
```

### Step-by-Step Migration

> **Note on Custom Domains:** If your blog uses a custom domain (like `https://blawg.com`), you should use the original Typepad URL for the first two steps and your custom domain for the last step.
>
>   - **Step 1** should use the `.typepad.com` URL (e.g., `https://blawg.typepad.com/blawg/`) to ensure all posts are found.
>   - **Step 2** should use the `.typepad.com` URL (e.g., `https://blawg.typepad.com/blawg/`)
>   - **Step 4** should use the final custom domain URL (e.g., `https://blawg.com`) so all links are rewritten correctly for your new site (we're making the links relative, so need to be able to filter by the url that Typepad was using)

> **Note on Drafts/Unpublished Posts:**
> This only gets published posts\! You might want to check your blog (edit panel) for unpublished drafts\!

> **Note on Comments:**
> By default this does not get comments, it's possible to do but advanced. You might want to pull a Typepad export which will contain comments\!


#### Step 1: Discover All Posts

Find and catalog every post URL on your blog:

```bash
python 01_get.py "https://yourblog.typepad.com/blog/"
```

**For password-protected blogs:**

```bash
python 01_get.py "https://yourblog.typepad.com/blog/" --username your_username --password your_password
```

**Output:** Creates `permalinks.txt` containing all post URLs

#### Step 2: Archive Posts and Media

Download all posts and their associated media:

```bash
python 02_posts.py "https://yourblog.typepad.com/blog/"
```

**For password-protected blogs:**

```bash
python 02_posts.py "https://yourblog.typepad.com/blog/" --username your_username --password your_password
```

**Output:** Creates `posts/` folder with your complete archive

#### Step 3: Prepare Media Files

Organize and optimize media for WordPress:

```bash
python 03_prepare_media.py
```

**Output:** Creates `wordpress_export/typepad_media/` with cleaned, de-duplicated media

#### Step 4: Generate WordPress Import File

Create the final import file:

```bash
python 04_create_wordpress_file.py --blog_url "https://yourblog.typepad.com/blog/"
```

**For large blogs**, split into multiple files:

```bash
python 04_create_wordpress_file.py --blog_url "https://yourblog.typepad.com/blog/" --max-posts-per-file 100
```

**Output:** Creates `wordpress_export/import.xml` (or multiple parts if split)

### Step 5: Import to WordPress 🎉

1.  **Upload Media**: Using FTP or your host's file manager, upload the `typepad_media` folder to `wp-content/uploads/`

2.  **Import Content**:

      * Navigate to WordPress Admin → Tools → Import
      * Select "WordPress" and install the importer if needed
      * Upload your `import.xml` file
      * Follow the prompts to complete the import

3.  **Configure Permalinks**: Go to Settings → Permalinks and select "Post name" to maintain URL structure

## 🔄 Re-running the Scripts (Starting Over)

This project is in active development, if you need to stop and re-run everything, you should first delete all the files and folders created by the scripts. This ensures you start with a clean slate.

You can safely delete the following items using your computer's file explorer:

**Folders to Delete:**

  * `posts/`
  * `raw-paged-data/`
  * `wordpress_export/`

**Files to Delete:**

  * `downloaded_permalinks.txt`
  * `scanned.txt`
  * `permalinks.txt` **Note:** Deleting `permalinks.txt` is usually fine, as the first script will create it again. However, if you created this file manually with a custom list of posts, you should **not** delete it.

## ❓ Common Issues & Solutions

### Files are saving in the wrong location

The easiest way to make sure everything saves in the right place is to put all the Python script files (`01_get.py`, `02_posts.py`, etc.) into the folder where you want your blog archive to be created. Then, open your terminal or command prompt inside that same folder to run the commands.

### Extra content (sidebars, footers) in posts

The script uses an automated system to find your main post content. If it includes extra parts of the page, you can fix it by telling it the content's specific CSS class.

1.  Open one of your saved HTML post files in a web browser.
2.  Right-click on the main text of your post and choose "Inspect" or "Inspect Element".
3.  Look for the HTML tag (usually a `<div>`) that wraps all of your post content and find its `class` name (e.g., `<div class="entry-body">` or `<div class="content">`).
4.  Re-run step 4 with the `--post-container-class` flag, using the name you found:
    ```bash
    python 04_create_wordpress_file.py --blog_url "..." --post-container-class "your-class-name"
    ```

### "python" command not found

Use `python3` instead of `python` on macOS and Linux:

```bash
python3 01_get.py "https://yourblog.typepad.com/blog/"
```

Of course\! Here is a new section for your README file based on your notes. It's written to match the style and tone of the rest of the document.

You can add this to your `README.md` file, maybe right after the "Common Issues & Solutions" section.

-----

## 💬 A Note on Importing Comments

By default, this tool **does not** import blog comments. Comments are often mixed with the blog's theme in complex ways, making them difficult to extract automatically.

It is possible to capture comments, but it is an **advanced method** that requires manual cleanup after the scripts are finished.

### How to Capture Comments

1.  Similar to the issue with extra sidebars, you need to find a CSS class that wraps **both** your main post content and the comments section. You can find this using your browser's "Inspect Element" tool.
2.  Run Step 4 using the `--post-container-class` flag with the class name you found. This tells the script to save a bigger chunk of the page.
    ```bash
    python 04_create_wordpress_file.py --blog_url "..." --post-container-class "your-wider-class-name"
    ```

### The Manual Cleanup Step

  * This process will save the comments inside your post content, but it will likely include a lot of extra, messy HTML from your Typepad theme.
  * You will need to manually edit the final `import.xml` file using a text editor before you upload it to WordPress.
  * Cleaning the file usually requires using **regular expressions (regex)** to find and replace the unwanted code.

> **Warning:** This is a difficult step. The specific regex needed for cleanup will be unique to your blog's theme. This process is recommended only for users comfortable with regex and manually editing XML files. I have included a text file 'regex_examples.txt' as and example of the cleanup I did for a blog, but your blog will be different. On each of the find and replace lines you should remove both the letter, colon and space before the find and replace i.e. "f: in <a[^>]*>[^<]*</a>..." to "in <a[^>]*>[^<]*</a>".

## 🔧 Technical Details

This tool is a collection of four Python scripts designed to run in sequence. Each script performs a distinct part of the migration process and saves its progress, allowing for a resilient and efficient workflow.

  - **Multi-threaded Downloads**: The archiving script uses multiple concurrent threads to download posts and media, significantly speeding up the process for large blogs.
  - **Split Export Support**: The export script can automatically split a very large blog into multiple smaller XML files to avoid timeouts during the WordPress import process.
  - **Resume Capability**: Each script logs its progress (`scanned.txt`, `downloaded_permalinks.txt`). If a script is stopped, it can be restarted and will resume from where it left off, skipping already completed work.

### Script-by-Script Breakdown

#### 01\_get.py - Post Discovery

This script acts as a web crawler to discover the URL of every single post on your blog.

  - **Mechanism**: It starts on page 1 of your blog's archive and scrapes it for links. It then looks for the "Next" page link and follows it, repeating the process until it can no longer find a "Next" link.
  - **Link Identification**: It specifically looks for `<a>` tags where the link text is exactly "Permalink", a common pattern in Typepad themes.
  - **Technology**: Uses `curl_cffi` to impersonate a real web browser, reducing the chance of being blocked. HTML is parsed with `BeautifulSoup`.
  - **Output**: A simple text file named `permalinks.txt` containing one post URL per line.
  - **Command Line Options**:
      - `blog_url`: (Required) The main URL of your blog, like `"https://yourblog.typepad.com/blog/"`.
      - `--sleep-time <seconds>`: The amount of time to wait between fetching pages. Default is `0.5`.
      - `--debug`: Shows extra detailed information while the script is running.
      - `--username <username>`: Username for password-protected blogs (if required).
      - `--password <password>`: Password for password-protected blogs (if required).

#### 02\_posts.py - Content Archiving

This script reads the list of URLs from `permalinks.txt` and downloads the full content for each post.

  - **Mechanism**: It uses a `ThreadPoolExecutor` to run multiple downloads in parallel. For each post URL, it downloads the main HTML file, all associated media (images, PDFs), and site-wide assets (CSS, JS).
  - **Asset Handling**: It parses the HTML to find all `<img>`, `<link>`, and `<script>` tags. It also recursively scans CSS files for `@import` and `url()` references to download fonts and background images.
  - **File Organization**: Each post is saved as an `.html` file. Media found within that post is saved to a correspondingly named sub-folder. Site-wide assets are saved to a shared `posts/assets` directory.
  - **Output**: The `posts/` directory, containing a complete, self-contained archive of your blog.
  - **Command Line Options**:
      - `blog_url`: (Required) The main URL of your blog.
      - `--threads <number>`: How many downloads to run at the same time. Default is `4`.
      - `--sleep-time <seconds>`: How long each worker should wait after downloading a post. Default is `0.5`.
      - `--debug`: Shows extra detailed information, which can be helpful for troubleshooting.
      - `--username <username>`: Username for password-protected blogs (if required).
      - `--password <password>`: Password for password-protected blogs (if required).

#### 03\_prepare\_media.py - Media Processing

This script processes the raw archive in the `posts/` directory to prepare all media for a clean WordPress import.

  - **Mechanism**: It scans for every non-HTML file and processes it. Its primary goals are to de-duplicate files and give them sane, unique filenames.
  - **Image De-duplication**: The script uses **perceptual hashing** via the `imagehash` library. It creates a unique "fingerprint" for each image. If it encounters a new image with a nearly identical fingerprint to one it's already seen (even if it's a different file size or format), it treats it as a duplicate and reuses the existing file. This is highly effective at reducing clutter.
  - **File Renaming**: All unique media files are copied to a single folder and given a descriptive, web-safe name based on the post they came from (e.g., `my-first-post_header-image.jpg`).
  - **Technology**: Uses `Pillow` and `imagehash` for image processing and `python-magic` to reliably identify file types regardless of their extension.
  - **Output**: The `wordpress_export/typepad_media/` folder containing all unique media, and a `file_map.json` file that maps every original file path to its new, final filename.
  - **Command Line Options**:
      - This script takes no command line options. It automatically finds the `posts/` folder and creates the `wordpress_export/` folder.

#### 04\_create\_wordpress\_file.py - WordPress Export Generation

The final script converts the cleaned HTML archive into a WordPress-compatible XML (WXR) import file.

  - **Mechanism**: It processes each `.html` file in parallel using a `ProcessPoolExecutor`. For each post, it extracts the title, author, and publication date, and performs an advanced cleaning of the main content.
  - **Intelligent Content Extraction**: It uses a multi-stage process to isolate the main article text:
    1.  It first checks if the user specified a CSS class with `--post-container-class`.
    2.  If not, it uses the `trafilatura` library, a powerful tool designed to extract the core content from a webpage while discarding boilerplate like ads, headers, and navigation.
    3.  As a fallback, it looks for common Typepad content classes like `.entry-body`.
  - **Link Rewriting**: This is a critical step. The script reads the `file_map.json` created by the previous script. It parses the post's HTML and replaces every old, local link to an image or file with its new, final URL in the WordPress uploads directory. It also rewrites links between your blog posts to use the standard WordPress slug format.
  - **Output**: An `import.xml` file (or multiple parts for large blogs) in the `wordpress_export` directory, ready to be uploaded to WordPress.
  - **Command Line Options**:
      - `--blog_url <url>`: (Required) The original root URL of your blog. Needed to fix links between posts.
      - `--blog_title <title>`: Sets the title for your blog in the export file.
      - `--post-container-class <class_name>`: Tells the script the specific CSS class that wraps your main post content to fix issues with sidebars being included.
      - `--max-posts-per-file <number>`: Splits the export into multiple smaller files, each with this many posts. Useful for very large blogs to prevent import timeouts.
      - `--disable-intelligent-text-extract`: Turns off the smart content finder and only uses manual rules.
      - `--disable-popup-scrubbing`: Stops the script from removing links that open images in a popup window.
      - `--disable-div-rm`: Stops the script from removing `<div>` tags from your post content.
      - `--disable-br-rm`: Stops the script from removing `<br>` tags and extra spaces.
      - `--debug`: Shows extra detailed information, especially for date parsing.