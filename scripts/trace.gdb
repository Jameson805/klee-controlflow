set logging redirect on
set logging file /dev/null

set logging enabled on
start
set logging enabled off

while ($_thread)
	printf "0x%lx\n", $pc
	set logging enabled on
	stepi
	set logging enabled off
end
