SELECT 'comment' AS item_type, 
       id,
       '' AS title,
       body,
       author,
       subreddit,
       parent_id,
       parent_clean_id,
       parent_comment_id,
       parent_post_id,
       approved,
       removed,
       num_reports,
       'https://reddit.com' || permalink AS permalink,
       NULL AS target_url,
       score,
       quarantine,
       distinguished
FROM   comments
UNION ALL 
SELECT 'post' AS item_type,
       id,
       title,
       selftext AS body,
       author,
       subreddit,
       null as parent_id,
       null as parent_clean_id,
       null as parent_comment_id,
       null as parent_post_id,
       approved,
       removed,
       num_reports,
       'https://reddit.com' || permalink AS permalink,
       url AS target_url,
       score,
       null as quarantine,
       distinguished
FROM   posts 

-- posts.url is just the permalink with https:// 
-- except for link posts, in which case it is the destination 
