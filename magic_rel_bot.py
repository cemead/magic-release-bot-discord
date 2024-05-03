import discord
from discord.ext import commands
import sqlite3
from datetime import datetime, timedelta
import requests
import re
from bs4 import BeautifulSoup
import asyncio
import mrb_config

# Create an instance of Intents
intents = discord.Intents.default()
intents.message_content = True

# Remove the default help command
bot = commands.Bot(command_prefix=';', intents=intents, help_command=None)
bot.remove_command('help')

# Create a connection to the SQLite database
conn = sqlite3.connect('mtg_sets.db')
cursor = conn.cursor()

# Create a table to store MTG sets if it doesn't exist
cursor.execute('''
    CREATE TABLE IF NOT EXISTS mtg_sets (
        set_code TEXT PRIMARY KEY,
        set_name TEXT,
        release_date TEXT,
        preview_date TEXT,
        blog_link TEXT
    )
''')
conn.commit()

# Make sure the URL is from the official Wizards of the Coast Magic site
def validate_url(url):
    return url.startswith("https://magic.wizards.com")


# Try fetching the site content
def fetch_site_content(ctx, url):
    response = requests.get(url)
    # Make sure the site is up
    if response.status_code == 200:
        return response.content
    else:
        # If it's not up, send an error message
        ctx.send("Failed to retrieve WoTC content.")
        return False

# Pull the set name from the HTML
def extract_set_name(html_content):
    soup = BeautifulSoup(html_content, 'html.parser')
    # Use regex to find the words in the title between "First Look at" and before |, if there is one
    pattern = r"(?:First Look at\s+)(.*?)(?:\s+\|.*|$)"
    title_element = soup.find('title')
    if title_element:
        title_text = title_element.text
        match = re.search(pattern,title_text)
        if match:
            return match.group(1)
    return None

# Pull the set code
def extract_set_code(content_str, set_name):
    # it might be in the a id of the website in the inner html
    set_code_pattern_1 = r"<p><strong>Website<\/strong>: <a id=\"daily-([a-z,0-9]+)\""
    # or maybe in the keywords hidden in the header
    set_code_pattern_2 = r"keywords=\"([a-zA-Z0-9]+),"
    match = re.search(set_code_pattern_1, content_str)
    if match:
        return match.group(1).upper()
    match = re.search(set_code_pattern_2, content_str)
    if match:
        return match.group(1).upper()
    return None

# Pull the publishing date
def extract_pub_date(content_str):
    # ReGex as it'll be in the "datePublished"
    pub_date_pattern = r"\"datePublished\":\s\"([\d]{4}-[\d]{2}-[\d]{2})"
    match = re.search(pub_date_pattern, content_str)
    if match:
        pub_date_str = match.group(1)
        pub_date = datetime.strptime(pub_date_str, "%Y-%m-%d")
        return pub_date

# Adjust the release/preview date as compared to the publishing date
def interpret_date(content_str, date_pattern):
    pub_date = extract_pub_date(content_str)
    match = re.search(date_pattern, content_str)
    if match:
        release_date_str = match.group(1)
        release_date = datetime.strptime(release_date_str, "%B %d")
        # If the publishing date is in the last quarter of the year, and the preview/release date is early in the year, adjust the year to be the next year in prep for display
        if release_date.month in [1, 2, 3] and pub_date.month in [10, 11, 12]:
            release_year = pub_date.year + 1
        else:
            release_year = pub_date.year
        return release_date.strftime(f"{release_year}-%m-%d")
    return None

# Pull the preview date from the page
def extract_preview_date(content_str):
    preview_date_pattern = r"Previews Begin\s*:?[^:]*:\s*(\w+\s+\d+)"
    # interpret it to see if it comes out the next year
    return interpret_date(content_str, preview_date_pattern)

# Pull the release date from the page
def extract_release_date(content_str):
    release_date_pattern_1 = r"Tabletop Launch\s*:?[^:]*:\s*(\w+\s+\d+)"
    release_date_pattern_2 = r"Tabletop Release\s*:?[^:]*:\s*(\w+\s+\d+)"

#   interpret it to see if it comes out the next year
    release_date = interpret_date(content_str, release_date_pattern_1)
    if release_date:
        return release_date

    return interpret_date(content_str, release_date_pattern_2)

# Analyze the page by combining the functions
async def page_analysis(ctx, content_str, pub_date):
    try:
        set_name = extract_set_name(content_str)
        # if there is no set name, error out
        if set_name is None:
            raise ValueError("Unable to pull set name from page. Please ping Lee if set is from 2023 or later.")
            return None

#       pull the set code, preview date, release date
        set_code = extract_set_code(content_str, set_name)
        preview_date = extract_preview_date(content_str)
        release_date = extract_release_date(content_str)

        # Return the values as a tuple
        return set_name, set_code, preview_date, release_date


        # print if there's an exception to the error, return None for all of the values to prevent future errors
    except Exception as e:
        await ctx.send(f"An error occurred: {str(e)}")
        return None, None, None, None  # Return default values in case of an error


# Delete released sets a week after release
async def delete_old_sets():
    # Calculate the date one week ago
    one_week_ago = datetime.now() - timedelta(days=7)

    # Query the database for sets released more than a week ago
    cursor.execute('SELECT * FROM mtg_sets WHERE release_date <= ?', (one_week_ago,))
    old_sets = cursor.fetchall()

    # Delete old sets from the database
    for old_set in old_sets:
        set_code = old_set[0]
        cursor.execute('DELETE FROM mtg_sets WHERE set_code = ?', (set_code,))
        conn.commit()

# Schedule the delete_old_sets function to run daily
async def schedule_delete_old_sets():
    while True:
        await delete_old_sets()
        # Wait for 24 hours before running the function again
        await asyncio.sleep(24 * 60 * 60)

# Start the background task
async def start_background_task():
    bot.loop.create_task(schedule_delete_old_sets())

# Call the start_background_task function when your bot starts running
@bot.event
async def on_ready():
    await start_background_task()

# Addset command
@bot.command(name='addset')
async def add_set(ctx, site):
    # Return help text if the user types ;addsite help
    if site == 'help':
        help_text= 'Please provide an official WotC link to add the set to the data base. \n Example: `;addset https://magic.wizards.com/en/news/announcements/a-first-look-at-wilds-of-eldraine`'
        await ctx.send(help_text)
        return None
    # Validate official link
    if not validate_url(site):
        await ctx.send('Invalid WoTC link. Please provide an official WotC site.')
        return
    # pull the site content
    html_content = fetch_site_content(ctx, site)
    if html_content:
        content_str = html_content.decode('utf-8')  # Decode bytes to string
        pub_date = extract_pub_date(content_str)
        # Give an error page if the publishing year is prior to page standardization
        # Won't be able to pull relevant details anyway
        if pub_date.year < 2023:
            await ctx.send('Set announced prior to page standardization - Cannot pull relevant details.')
            return
        else:
            # Pull the set name, code, preview date, and release date from the page
            set_name, set_code, preview_date, release_date = await page_analysis(ctx, content_str, pub_date)
            # Error out if there is no relevant set code
            if set_code == None:
                await ctx.send("Unable to pull set code. Double-check the page?")
                return

#           Check to see if the set code is already in the database
            cursor.execute('SELECT set_code FROM mtg_sets WHERE set_code = ?', (set_code,))
            existing_set = cursor.fetchone()
            # if it already exists in the database, bring up the ;findset command for it
            if existing_set:
                await ctx.send(f'The set code {set_code} already exists in the database.')
                await ctx.invoke(find_set, set_code=set_code)
                return

        # Insert the set into the database
        cursor.execute('''
        INSERT INTO mtg_sets (set_code, set_name, preview_date, release_date, blog_link)
        VALUES (?, ?, ?, ?, ?)
    ''', (set_code, set_name, preview_date, release_date, site))
        conn.commit()
        await ctx.send(f'{set_code} **{set_name}** has been added to the database.')
    else:
        print("Error retrieving site content")


# Findset command
@bot.command(name='findset')
async def find_set(ctx, set_code):
    set_code = set_code.upper()
    # Check if the MTG set exists in the database
    cursor.execute('SELECT * FROM mtg_sets WHERE set_code = ?', (set_code,))
    result = cursor.fetchone()

    # If there is a result, add it to the embed
    if result:
        set_code, set_name, preview_date, release_date, blog_link = result
        embed = discord.Embed(title=f'{set_name} ({set_code})', color=0x228B22)
        embed.add_field(name='Previews Begin',
                        value=preview_date, inline=False)
        embed.add_field(name='Release Date', value=release_date, inline=False)
        embed.add_field(name='Source Link', value=blog_link, inline=False)
        # Send the embed generated from the combination of fields
        await ctx.send(embed=embed)
        # Send a message if the set code is not in database
    else:
        await ctx.send(f'{set_code} not found. Add it through at `;addset`?')

@bot.command(name='listsets')
async def list_sets(ctx):
    # Fetch all records from the mtg_sets table
    cursor.execute('SELECT * FROM mtg_sets')
    results = cursor.fetchall()

    if not results:
        await ctx.send('No MTG sets found in the database.')
    else:
        embed = discord.Embed(title='List of Upcoming Sets', color=0x228B22)

        for result in results:
            set_code, set_name, preview_date, release_date, blog_link = result
            embed.add_field(
                name=f'{set_name} ({set_code})',
                value=f'Previews Begin: {preview_date}\nRelease Date: {release_date}\nSource Link: {blog_link}',
                inline=False
            )

        await ctx.send(embed=embed)


@bot.command(name='delset')
async def delete_set(ctx, set_code):
    if set_code == 'help':
        embed = discord.Embed(title='Delete Set Help', color=0x228B22)
        embed.add_field(name='',value='Deletes sets from list using set code\n*Example*:`;delset ody`')
        embed.add_field()
        await ctx.send(embed)
    # Check if the set exists in the database
    cursor.execute('SELECT * FROM mtg_sets WHERE set_code = ?', (set_code,))
    result = cursor.fetchone()

    if result:
        # Delete the set from the database
        cursor.execute('DELETE FROM mtg_sets WHERE set_code = ?', (set_code,))
        conn.commit()
        await ctx.send(f'{set_code} has been deleted from the database.')
    else:
        await ctx.send(f'{set_code} not found.')

@bot.command(name='credits')
async def add_set(ctx):
    embed = discord.Embed(title='Credits', color=0x228B22)
    embed.add_field(
        name=f'Magic Releases Bot v. 2.0',
        value=f'Code by Lee. Moral support by [Mack](https://i.imgur.com/jvsqamJ.jpeg).',
        inline=False
        )
    await ctx.send(embed=embed)

@bot.command(name='help')
async def add_set(ctx):
     embed = discord.Embed(title='List of Functions', color=0x228B22)
     embed.add_field(
         name=f'Magic Releases Bot Commands',
         value=f'`;addset https://www.magic.wizards.com/... - Adds a set to release list\n`;listsets` - Returns a list of upcoming sets\n `;findset [set code]` - Returns information about a set from database\n`;delset [set code]` - Deletes a set listing from database\n`;credits` - Lists credits',
         inline=False
         )

     await ctx.send(embed=embed)



# Add more commands and events as needed


# Pull the API key from the mrb_config file
bot.run(mrb_config.api_key)

# Close the database connection when the bot is shutting down
conn.close()
