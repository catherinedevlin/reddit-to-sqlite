# reddit-to-sqlite
Save data from Reddit to SQLite. Dogsheep-based.

Inserts records of posts and comments into a SQLite database.  Can 
be run repeatedly safely; will refresh already-saved results (see Reload, below).
Creates `posts` and `comments` tables, plus an `items` view with a unified 
view.

## Usage


    reddit-to-sqlite r/python
    reddit-to-sqlite u/catherinedevlin 
    reddit-to-sqlite --help 

By default, writes to a local `reddit.sqlite` database (change with `--db`).

## Authorizing

reddit-to-sqlite will look for a file of authorization info (location determined 
by --auth, defaults to `~/.config/reddit-to-sqlite.json`) and, if not found, will 
query the user and then save the info there.  You will need a Reddit username and 
password, and you will need to 
[register your app with Reddit](https://www.reddit.com/wiki/api) to get a client_id 
and client_secret.  ([More instructions](https://www.geeksforgeeks.org/how-to-get-client_id-and-client_secret-for-python-reddit-api-registration/))

## Limits

Whether used for users or for subreddits, can't guarantee getting all 
posts or comments, because

- Reddit's API only supplies the last 1000 items for each API call, and does 
not support pagination; 
- Comments nested under a single post won't be retrieved if they are deeply 
nested in long comment chains 
(see [replace_more](https://praw.readthedocs.io/en/latest/tutorials/comments.html#the-replace-more-method)) 

## Reload 

reddit_to_sql can be run repeatedly for a given user or subreddit, replacing previously saved 
results each time.  However, to save excessive API use, it works backward through time and 
stops after it reaches the timestamp of the last saved post, plus an overlap period (default 
7 days).  That way, recent changes (scores, new comments) will be recorded, but older ones
won't unless `--post_reload` is increased.  If posts keep getting comments of interest long 
after they are posted, you can increase `--post_reload`. 

When loading an individual user's comments, by default reddit_to_sql stops just 1 day after 
reaching the most recent comment that is already recorded in the database.  However, if you're 
interested in comment scores, you may want to impose a longer `--comment_reload`, since scores 
may keep changing for longer than a single day after the comment is posted.
