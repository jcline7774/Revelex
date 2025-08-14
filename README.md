# Revelex
GPS Road Search

This repo contains 2 python files for running a road search.  The search area is limited to the USA. 
- jmc_rev_roadsearch.py was created using an http call to the overpass API directly.
- jmc_rev_search2.py is an identical file but it was functions by using the overpy library to contact the API

I made 2 versions because initially I was having trouble using the main overpass api and had to call a mirror site to stop the program from timing out. Both seem to work equally well.

All results will print to console as well as to a json file that will store itself in a local directory.

- To run a command line search, download the file use the following string from the download directory:
  python <filename> <roadway_name> <city> <state> + Enter
- I95 in Miami Example: 
  python jmc_rev_roadsearch.py 'I 95' 'Miami' 'Florida'

Note:
I felt this format was best to allow search customization.  I have other versions where the location and street are coded into the file as well as files that have the seach location set to smaller areas, ie. counties in south Florida, ranges from Florida to S. Carolina, east coast corridor but their use is limited.
