iNaturalist Query Format
The iNaturalist query format is intended to be an easy to write query format for the iNaturalist observations API. Its basic structure consists of a JSON dictionary, with zero or more top-level keys that are search parameters. Only the parameters listed under "Parameter reference" below can be used. The API silently ignores any parameter it does not know, so never invent parameters.
A basic multi-parameter query looks like this:

```
{
  "taxon_name": "Rattus rattus",
  "photos": true,
  "quality_grade": "research"
}
```

That query will look for observations of Rattus rattus that have photos and are research grade.
Multiple parameters are combined with the "AND" operator.
More details on the query types supported below. Note, the query types under "All Parameters" work on any parameter. The query types under the other sections only work with parameters of the matching type.

All Parameters
Searching for a value

```
{
  "taxon_name": "Rattus rattus"
}
```

Searching for multiple values (only "iconic_taxa" accepts a list, and any of the listed values match)

```
{
  "iconic_taxa": ["Aves", "Mammalia"]
}
```

Free text searching (use only when no other parameter fits)

```
{
  "q": "nest"
}
```

Boolean Parameters
Searching for observations that have a property

```
{
  "photos": true
}
```

Searching for observations that do NOT have a property

```
{
  "photos": false
}
```

Numeric Parameters
Searching for a whole year, a month of any year, a day of the month or an hour of the day

```
{
  "year": 2020,
  "month": 6
}
```

Date Parameters
Searching within a range on the observation date ("d1" is on or after, "d2" is on or before)

```
{
  "d1": "2020-03-01",
  "d2": "2020-05-31"
}
```

Searching for one exact date

```
{
  "observed_on": "2020-06-15"
}
```

Geographic Parameters
Searching within a radius (in kilometers) around a point

```
{
  "lat": 40.71,
  "lng": -74.0,
  "radius": 25
}
```

Searching within a bounding box

```
{
  "nelat": 30.0,
  "nelng": -80.0,
  "swlat": 25.0,
  "swlng": -87.0
}
```

## Parameter reference
Set only the parameters the request needs. Unset parameters are not sent.

### Taxon

- `taxon_name`: A scientific or common name. Includes descendant taxa, so "Aves" matches all birds and "Rattus"
  matches every species in the genus. A common name can match several taxa.
- `taxon_id`: A numeric taxon ID. Only set it when the request gives the ID. Never guess it.
- `without_taxon_id`: Exclude this taxon ID and its descendants. Only set it when the request gives the ID.
- `iconic_taxa`: A list of broad groups. Allowed values: Plantae, Animalia, Mollusca, Reptilia, Aves, Amphibia,
  Actinopterygii, Mammalia, Insecta, Arachnida, Fungi, Protozoa, Chromista, unknown. Observations of any listed group
  match.
- `rank`: Only observations identified to this taxonomic rank, such as species, genus or family.
- `q`: Free-text search. Use it only when no other parameter fits.

### Observer, place, project, list

- `user_login`: The observer's login name.
- `place_id`: A numeric place ID. Only set it when the request gives the ID. Never guess it.
- `project_id`: A project ID or slug. Only set it when the request gives it.
- `list_id`: A numeric list ID. Matches observations of taxa on that list, from anywhere in the world. This filters
  by taxon, not by location. Only set it when the request gives the ID.

### Location

- `lat`, `lng`, `radius`: Observations within `radius` kilometers of a point. Set all three together.
- `nelat`, `nelng`, `swlat`, `swlng`: A bounding box. Set all four together.

### Time

- `observed_on`: One exact date, in yyyy-mm-dd format.
- `d1`, `d2`: Observed on or after `d1`, and on or before `d2`. Both in yyyy-mm-dd format.
- `year`, `month`, `day`, `hour`: Observed in that year (for example 2022), month of any year (1-12), day of the month
  (1-31) or hour of the day (0-23). Use these for a whole year or month. Do not give partial dates to `observed_on`,
  `d1` or `d2`.
- `updated_since`: Updated on or after this date, in yyyy-mm-dd format.

### Evidence and status

- `photos`, `sounds`: true for observations that have photos or sounds. false for observations that do not.
- `geo`: true for observations that have coordinates.
- `captive`: true for captive or cultivated observations.
- `native`, `introduced`, `out_of_range`: true for taxa that are native, introduced or outside their known range
  at the observation location.
- `verifiable`: true for observations whose quality grade is needs_id or research.
- `quality_grade`: One of research (community-verified), needs_id (awaiting identification) or casual (missing
  evidence or flagged). Leave it unset unless the request asks for it.
- `geoprivacy`: One of open, obscured, private, obscured_private.
- `license`, `photo_license`: One of cc-by, cc-by-nc, cc-by-nd, cc-by-sa, cc-by-nc-nd, cc-by-nc-sa, cc0.

### Paging and order

- `per_page`: Number of results to return, from 1 to 200. The default is 200.
- `order_by`: One of created_at, observed_on, id.
- `order`: asc or desc.

### Boolean values

Boolean parameters are true or false. Never set a boolean parameter to false unless the request asks to exclude
that property.
