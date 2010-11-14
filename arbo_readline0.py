
import sys

def readline0(file=sys.stdin, separator='\0', blocksize=65536):
	# this function assumes that there will be a null once in a while.  If you feed it with a huge block of data that has
	# no nulls, woe betide you.
	buffer = ''
	fields = []
	while True:
		block = file.read(blocksize)
		if fields[0:]:
			# nth time through loop, n>=2
			if buffer[-1:] == separator:
				# buffer ended in a null byte, so we need to yield a null string, and buffer is the block
				if not block:
					break
				else:
					buffer = block
			else:
				# buffer did not end in a null byte, so we have a partial element to return that needs to be saved
				if not block:
					yield fields[-1]
					break
				else:
					buffer = fields[-1] + block
		else:
			# first time through the loop - an empty block is an empty input
			# a nonempty block is something to part out
			if not block:
				break
			else:
				buffer = block
		fields = buffer.split(separator)
		for field in fields[:-1]:
			yield field
	raise StopIteration

