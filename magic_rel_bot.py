import discord
from discord.ext import commands
import sqlite3
from datetime import datetime
import os  
import mrb_config.py

# Create an instance of Intents
intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix=';', intents=intents)

# Create a connection to the SQLite database
conn = sqlite3.connect('mtg_sets.db')
cursor = conn.cursor()

# Create a table to store MTG sets if it doesn't exist
cursor.execute('''
    CREATE TABLE IF NOT EXISTS mtg_sets (
        set_abb TEXT PRIMARY KEY,
        set_name TEXT,
        release_date TEXT,
        preview_date TEXT,
        blog_link TEXT
    )
''')
conn.commit()

def validate_date_format(date_str):
    try:
        datetime.strptime(date_str, '%Y-%m-%d')
        return True
    except ValueError:
        return False

def validate_url(url):
    return url.startswith("https://magic.wizards.com")

@bot.command(name='addset')
async def add_set(ctx, *, set_info):
    # Split the arguments into individual components
    args_list = []
    inside_quotes = False
    current_arg = ""
    loop = -1
    
    if set_info.startswith("help"):
        await ctx.send(f'`;addset setcode "Title of the Set" (preview date) (release date) (WotC announcement page)`')
        example = '```;addset mack "Makkurosuke the Cat" 2014-03-14 2018-03-21 https://en.wikipedia.org/wiki/Susuwatari```'
        embed = discord.Embed(title="Add Set Command Help", color=0x7289DA)
        embed.add_field(name="Example", value=example, inline=False)
        await ctx.send(embed=embed)
        return

    # Go through every character in the string
    for char in set_info:
        # update loop to see if you've reached the end of the string
        loop += 1

        # check to see if the space is inside quotes (to denote it as part of the title) or if it's one of the other arguments
        if char == ' ' and not inside_quotes:
            # add it to the args list if it is
            args_list.append(current_arg.strip())
            # remove current_arg to refill
            current_arg = ""
            
        # Check to see if the character is in quotes 
        # (for instances where the title is more than one word)
        elif char == '"':
            inside_quotes = not inside_quotes

        # if you're at the very end of the string, add the ending character to the current arg, add the current arg to the arg list, and break the loop
        elif len(set_info) == loop:
            current_arg += char
            args_list.append(current_arg.strip())
            break
        else:
            current_arg += char
    args_list.append(current_arg.strip())

  # Extract set name, preview_date, release_date, and blog_link
    set_abb = args_list[0]
    set_name = args_list[1]
    preview_date = args_list[2]
    release_date = args_list[3]
    blog_link = args_list[4]
    
    # Validate date format before adding to the database
    if not validate_date_format(release_date) or not validate_date_format(preview_date):
        await ctx.send('Invalid date format. Please use YYYY-MM-DD.')
        return

    # Validate official link
    if not validate_url(blog_link):
        await ctx.send('Invalid blog link. Please provide an official WotC site.')
        return

    # Insert the set into the database
    cursor.execute('''
        INSERT INTO mtg_sets (set_abb, set_name, preview_date, release_date, blog_link)
        VALUES (?, ?, ?, ?, ?)
    ''', (set_abb, set_name, preview_date, release_date, blog_link))
    conn.commit()
    await ctx.send(f'{set_abb} **{set_name}** has been added to the database.')
        

# return a set from the database with ;findset
@bot.command(name='findset')
async def find_set(ctx, set_abb):
    # Check if the set exists in the database
    cursor.execute('SELECT * FROM mtg_sets WHERE set_abb = ?', (set_abb,))
    # assign the record to "result"
    result = cursor.fetchone()

    if result:
        set_abb, set_name, preview_date, release_date, blog_link = result
        embed = discord.Embed(title=f'{set_name} ({set_abb})', color=0x00ff00)
        embed.add_field(name='Previews Begin', value=preview_date, inline=False)
        embed.add_field(name='Release Date', value=release_date, inline=False)
        embed.add_field(name='Source Link', value=blog_link, inline=False)
        await ctx.send(embed=embed)
    else:
        await ctx.send(f'{set_abb} not found. Add it through at `;addset`?')
        
@bot.command(name='listsets')
async def list_sets(ctx):
    # Fetch all records from the mtg_sets table
    cursor.execute('SELECT * FROM mtg_sets')
    results = cursor.fetchall()

    if not results:
        await ctx.send('No MTG sets found in the database.')
    else:
        embed = discord.Embed(title='List of Upcoming Sets', color=0x00ff00)

        for result in results:
            set_abb, set_name, preview_date, release_date, blog_link = result
            embed.add_field(
                name=f'{set_name} ({set_abb})',
                value=f'Previews Begin: {preview_date}\nRelease Date: {release_date}\nSource Link: {blog_link}',
                inline=False
            )

        await ctx.send(embed=embed)
        
@bot.command(name='delset')
async def delete_set(ctx, set_abb):
    # Check if the set exists in the database
    cursor.execute('SELECT * FROM mtg_sets WHERE set_abb = ?', (set_abb,))
    result = cursor.fetchone()

    if result:
        # Delete the set from the database
        cursor.execute('DELETE FROM mtg_sets WHERE set_abb = ?', (set_abb,))
        conn.commit()
        await ctx.send(f'{set_abb} has been deleted from the database.')
    else:
        await ctx.send(f'{set_abb} not found.')

# Add more commands and events as needed

# Pull the API key from the mrb_config file
bot.run(mrb_config.api_key)

# Close the database connection when the bot is shutting down
conn.close()

