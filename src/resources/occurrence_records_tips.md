* If the user places a search term in quotes, always use the full text that is quoted, do not break it up.
* If the user specifies a scientific name, such as the binomial "Homo sapiens", always put the whole name in "taxon_name". Do not split it into parts. "taxon_name" also matches the taxon's descendants, so "Rattus" matches every species in the genus.
* Common names such as "birds" or "trees" fit "iconic_taxa" (for example Aves or Plantae) better than "taxon_name".
* Never guess a numeric ID for "taxon_id", "place_id", "project_id" or "list_id". Only set one if the user states the ID. This tool cannot look up IDs from names.
* If the user names a place, such as a state or country, and does not give coordinates or a place ID, you cannot search by it. Use "lat", "lng" and "radius" for a point and distance, or the bounding box fields for an area, but only if the user gives the coordinates.
* Searching by observer name is unlikely to work. "user_login" only matches an exact login name, so only set it if the user gives a login.
* For a whole year or a whole month, use "year" or "month". Do not give partial dates like "2020" to "observed_on", "d1" or "d2". The API quietly returns wrong results for them. Use "d1" and "d2" for a date range, in yyyy-mm-dd format.
* Searching by lists performs an OR operation. For example, a search for "iconic_taxa":["Aves","Mammalia"] will return bird observations and ALSO mammal observations, it will NOT return observations where both occur together.
* "quality_grade" has three values: research (community-verified), needs_id (awaiting identification) and casual (missing evidence or flagged). Together they cover all observations. Only set it if the user asks for it.
* To get only observations that have photos, set "photos" to true. To get only observations without photos, set it to false. To get observations of any kind, leave it unset.
* "list_id" matches observations of taxa on a list, from anywhere in the world. It does not limit observations to a place.
* There are no parameters for image quality, image content, observer skill or how common a species is. Do not choose search parameters that only partially fulfill the user's request. Instead, you should abort (don't set any search parameters) and explain why.
* Only use the "per_page" field if the user explicitly asks to limit the amount of information retrieved. For example, if the user wants to know which species have the most observations, it's ok to retrieve the full list of species counts.
* At most 200 observations are returned per request. "total_results" in the response is the number of matching observations, which can be much larger.
* Photo URLs are in the artifact data at "results[].photos[].url". The size is part of the URL, for example "square". Replace only that word with "original", "large", "medium", "small" or "thumb" to get a different size.
* The API allows roughly 60 requests per minute. Do not send several searches when one will answer the request.
